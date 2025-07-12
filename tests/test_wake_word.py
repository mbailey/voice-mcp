"""Tests for wake word detection module."""

import os
import time
import threading
import numpy as np
import pytest
from unittest.mock import Mock, patch, MagicMock

from voice_mode.wake_word import (
    WakeWordState,
    WakeWordConfig, 
    SimpleWakeWordDetector,
    AudioBuffer,
    WakeWordDetectionService,
    get_wake_word_config
)


class TestWakeWordConfig:
    """Test wake word configuration."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = WakeWordConfig()
        assert config.wake_words == ["hey claude"]
        assert config.pause_command == "stand down"
        assert config.resume_command == "standby"
        assert config.sensitivity == 0.5
        assert config.sample_rate == 16000
        assert config.chunk_duration == 5.0
        assert config.chunk_overlap == 0.5
        assert config.context_seconds == 10.0
        assert config.local_stt_only is True
    
    def test_custom_wake_words(self):
        """Test custom wake words configuration."""
        config = WakeWordConfig(wake_words=["ok claude", "hello assistant"])
        assert len(config.wake_words) == 2
        assert "ok claude" in config.wake_words
        assert "hello assistant" in config.wake_words


class TestSimpleWakeWordDetector:
    """Test simple text-based wake word detector."""
    
    def test_detect_wake_word(self):
        """Test basic wake word detection."""
        config = WakeWordConfig(wake_words=["hey claude"])
        detector = SimpleWakeWordDetector(config)
        
        # Test exact match
        result = detector.detect("hey claude, what's the weather?")
        assert result == "hey claude, what's the weather?"
        
        # Test case insensitive
        result = detector.detect("Hey Claude, how are you?")
        assert result == "Hey Claude, how are you?"
        
        # Test no match
        result = detector.detect("hello there")
        assert result is None
    
    def test_detect_pause_command(self):
        """Test pause command detection."""
        config = WakeWordConfig(pause_command="stand down")
        detector = SimpleWakeWordDetector(config)
        
        result = detector.detect("stand down for now")
        assert result == "PAUSE"
        
        # Case insensitive
        result = detector.detect("Stand Down please")
        assert result == "PAUSE"
    
    def test_detect_resume_command(self):
        """Test resume command detection."""
        config = WakeWordConfig(resume_command="standby")
        detector = SimpleWakeWordDetector(config)
        
        result = detector.detect("standby mode")
        assert result == "RESUME"
    
    def test_command_priority(self):
        """Test that commands have priority over wake words."""
        config = WakeWordConfig(
            wake_words=["standby"],  # Same as resume command
            resume_command="standby"
        )
        detector = SimpleWakeWordDetector(config)
        
        # Should detect as RESUME command, not wake word
        result = detector.detect("standby mode")
        assert result == "RESUME"
    
    def test_multiple_wake_words(self):
        """Test detection with multiple wake words."""
        config = WakeWordConfig(wake_words=["hey claude", "ok claude", "claude"])
        detector = SimpleWakeWordDetector(config)
        
        assert detector.detect("hey claude, help me") is not None
        assert detector.detect("ok claude, what time is it?") is not None
        assert detector.detect("claude, can you hear me?") is not None
        assert detector.detect("hello computer") is None


class TestAudioBuffer:
    """Test circular audio buffer."""
    
    def test_buffer_creation(self):
        """Test buffer initialization."""
        buffer = AudioBuffer(duration_seconds=10.0, sample_rate=16000)
        assert buffer.buffer_size == 160000
        assert len(buffer.buffer) == 160000
        assert buffer.write_index == 0
    
    def test_write_audio(self):
        """Test writing audio to buffer."""
        buffer = AudioBuffer(duration_seconds=1.0, sample_rate=100)
        
        # Write some audio
        audio_chunk = np.ones(50, dtype=np.float32)
        buffer.write(audio_chunk)
        
        assert buffer.write_index == 50
        assert np.all(buffer.buffer[:50] == 1.0)
        assert np.all(buffer.buffer[50:] == 0.0)
    
    def test_circular_wrap(self):
        """Test circular buffer wrapping."""
        buffer = AudioBuffer(duration_seconds=1.0, sample_rate=100)
        
        # Fill buffer completely
        audio_chunk = np.ones(100, dtype=np.float32)
        buffer.write(audio_chunk)
        assert buffer.write_index == 0  # Wrapped around
        
        # Write more to test wrapping
        audio_chunk = np.ones(50, dtype=np.float32) * 2.0
        buffer.write(audio_chunk)
        assert buffer.write_index == 50
        assert np.all(buffer.buffer[:50] == 2.0)
        assert np.all(buffer.buffer[50:] == 1.0)
    
    def test_get_last_n_seconds(self):
        """Test retrieving last N seconds of audio."""
        buffer = AudioBuffer(duration_seconds=2.0, sample_rate=100)
        
        # Write 1 second of audio with value 1.0
        buffer.write(np.ones(100, dtype=np.float32))
        
        # Write 0.5 seconds of audio with value 2.0
        buffer.write(np.ones(50, dtype=np.float32) * 2.0)
        
        # Get last 0.5 seconds
        last_audio = buffer.get_last_n_seconds(0.5)
        assert len(last_audio) == 50
        assert np.all(last_audio == 2.0)
        
        # Get last 1 second
        last_audio = buffer.get_last_n_seconds(1.0)
        assert len(last_audio) == 100
        assert np.all(last_audio[:50] == 1.0)
        assert np.all(last_audio[50:] == 2.0)


class TestWakeWordDetectionService:
    """Test wake word detection service."""
    
    @pytest.fixture
    def mock_service(self):
        """Create a mock wake word detection service."""
        config = WakeWordConfig()
        stt_callback = Mock(return_value="test transcription")
        wake_callback = Mock()
        
        service = WakeWordDetectionService(config, stt_callback, wake_callback)
        return service, stt_callback, wake_callback
    
    def test_service_initialization(self, mock_service):
        """Test service initialization."""
        service, _, _ = mock_service
        
        assert service.state == WakeWordState.IDLE
        assert service.config.wake_words == ["hey claude"]
        assert len(service.text_buffer) == 0
    
    def test_state_transitions(self, mock_service):
        """Test service state transitions."""
        service, _, _ = mock_service
        
        # Can't start from non-idle state
        service.state = WakeWordState.STANDBY
        service.start()  # Should log warning
        
        # Reset to idle
        service.state = WakeWordState.IDLE
        
        # Test pause/resume
        service.state = WakeWordState.STANDBY
        service.pause()
        assert service.state == WakeWordState.PAUSED
        
        service.resume()
        assert service.state == WakeWordState.STANDBY
    
    def test_text_buffer_management(self, mock_service):
        """Test text buffer management."""
        service, _, _ = mock_service
        
        # Add some text entries
        with service.text_buffer_lock:
            service.text_buffer.append({
                'timestamp': time.time() - 70,  # Old entry
                'text': 'old text'
            })
            service.text_buffer.append({
                'timestamp': time.time() - 30,  # Recent entry
                'text': 'recent text'
            })
        
        # Process audio chunk to trigger cleanup
        mock_audio = np.zeros(1000, dtype=np.float32)
        service._process_audio_chunk(mock_audio)
        
        # Old entry should be removed
        with service.text_buffer_lock:
            assert len(service.text_buffer) >= 1
            assert all(item['text'] != 'old text' for item in service.text_buffer)
    
    def test_wake_word_detection_flow(self, mock_service):
        """Test wake word detection flow."""
        service, stt_callback, wake_callback = mock_service
        
        # Configure STT to return wake word
        stt_callback.return_value = "hey claude, what's the weather?"
        
        # Process audio chunk
        mock_audio = np.zeros(1000, dtype=np.float32)
        service.state = WakeWordState.STANDBY
        service._process_audio_chunk(mock_audio)
        
        # Wake callback should be called
        wake_callback.assert_called_once()
        call_args = wake_callback.call_args[0]
        assert "hey claude" in call_args[0].lower()
        assert "hey claude, what's the weather?" in call_args[1]
    
    def test_pause_command_detection(self, mock_service):
        """Test pause command detection."""
        service, stt_callback, wake_callback = mock_service
        
        # Configure STT to return pause command
        stt_callback.return_value = "stand down for a moment"
        
        # Process audio chunk
        service.state = WakeWordState.STANDBY
        service._process_audio_chunk(np.zeros(1000, dtype=np.float32))
        
        # Should be paused
        assert service.state == WakeWordState.PAUSED
        wake_callback.assert_not_called()
    
    @patch('sounddevice.InputStream')
    def test_audio_recording_loop(self, mock_input_stream, mock_service):
        """Test audio recording loop (basic coverage)."""
        service, _, _ = mock_service
        
        # Create mock context manager
        mock_stream_instance = MagicMock()
        mock_input_stream.return_value.__enter__.return_value = mock_stream_instance
        
        # Start service (in thread)
        service.stop_event.set()  # Set immediately to prevent hanging
        service._audio_recording_loop()
        
        # Verify InputStream was created with correct parameters
        mock_input_stream.assert_called_once()
        call_kwargs = mock_input_stream.call_args[1]
        assert call_kwargs['samplerate'] == 16000
        assert call_kwargs['channels'] == 1


class TestEnvironmentConfiguration:
    """Test environment variable configuration."""
    
    def test_default_env_config(self):
        """Test default configuration from environment."""
        config = get_wake_word_config()
        assert config.wake_words == ["Hey Claude"]
        assert config.pause_command == "stand down"
        assert config.resume_command == "standby"
        assert config.local_stt_only is True
    
    def test_custom_env_config(self):
        """Test custom configuration from environment."""
        with patch.dict(os.environ, {
            'VOICE_MODE_WAKE_WORD': 'Ok Claude, Hello Assistant',
            'VOICE_MODE_PAUSE_COMMAND': 'pause now',
            'VOICE_MODE_RESUME_COMMAND': 'continue',
            'VOICE_MODE_WAKE_SENSITIVITY': '0.8',
            'VOICE_MODE_WAKE_CONTEXT_SECONDS': '15',
            'VOICE_MODE_WAKE_LOCAL_ONLY': 'false'
        }):
            config = get_wake_word_config()
            assert len(config.wake_words) == 2
            assert "Ok Claude" in config.wake_words
            assert "Hello Assistant" in config.wake_words
            assert config.pause_command == "pause now"
            assert config.resume_command == "continue"
            assert config.sensitivity == 0.8
            assert config.context_seconds == 15.0
            assert config.local_stt_only is False