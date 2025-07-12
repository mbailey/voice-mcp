"""Wake word detection module for Voice Mode standby functionality."""

import asyncio
import logging
import os
import queue
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Callable, List, Dict, Any

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)


class WakeWordState(Enum):
    """States for wake word detection system."""
    IDLE = "idle"
    STANDBY = "standby"
    DETECTED = "detected"
    PAUSED = "paused"


@dataclass
class WakeWordConfig:
    """Configuration for wake word detection."""
    wake_words: List[str] = None
    pause_command: str = "stand down"
    resume_command: str = "standby"
    sensitivity: float = 0.5
    sample_rate: int = 16000
    chunk_duration: float = 10.0  # seconds
    chunk_overlap: float = 0.5   # seconds
    context_seconds: float = 10.0
    local_stt_only: bool = True
    
    def __post_init__(self):
        if self.wake_words is None:
            self.wake_words = ["hey claude"]


class SimpleWakeWordDetector:
    """Simple text-based wake word detector for MVP."""
    
    def __init__(self, config: WakeWordConfig):
        self.config = config
        self.wake_words_lower = [w.lower() for w in config.wake_words]
        self.pause_command_lower = config.pause_command.lower()
        self.resume_command_lower = config.resume_command.lower()
    
    def detect(self, text: str) -> Optional[str]:
        """
        Detect wake words or commands in text.
        
        Returns:
            - Wake word if detected
            - "PAUSE" for pause command
            - "RESUME" for resume command
            - None if nothing detected
        """
        text_lower = text.lower()
        
        # Check pause/resume commands first (higher priority)
        if self.pause_command_lower in text_lower:
            return "PAUSE"
        if self.resume_command_lower in text_lower:
            return "RESUME"
        
        # Check wake words
        for wake_word in self.wake_words_lower:
            if wake_word in text_lower:
                # Find position to extract context after wake word
                position = text_lower.index(wake_word)
                return text[position:]
        
        return None


class AudioBuffer:
    """Circular audio buffer for continuous recording."""
    
    def __init__(self, duration_seconds: float, sample_rate: int):
        self.sample_rate = sample_rate
        self.buffer_size = int(duration_seconds * sample_rate)
        self.buffer = np.zeros(self.buffer_size, dtype=np.float32)
        self.write_index = 0
        self.lock = threading.Lock()
    
    def write(self, audio_chunk: np.ndarray):
        """Write audio chunk to circular buffer."""
        with self.lock:
            chunk_size = len(audio_chunk)
            if chunk_size > self.buffer_size:
                # If chunk is larger than buffer, only keep the end
                audio_chunk = audio_chunk[-self.buffer_size:]
                chunk_size = self.buffer_size
            
            # Calculate how much space is left in buffer
            space_left = self.buffer_size - self.write_index
            
            if chunk_size <= space_left:
                # Chunk fits in remaining space
                self.buffer[self.write_index:self.write_index + chunk_size] = audio_chunk
                self.write_index = (self.write_index + chunk_size) % self.buffer_size
            else:
                # Chunk wraps around
                self.buffer[self.write_index:] = audio_chunk[:space_left]
                self.buffer[:chunk_size - space_left] = audio_chunk[space_left:]
                self.write_index = chunk_size - space_left
    
    def get_last_n_seconds(self, seconds: float) -> np.ndarray:
        """Get the last N seconds of audio from buffer."""
        with self.lock:
            samples_needed = int(seconds * self.sample_rate)
            if samples_needed > self.buffer_size:
                samples_needed = self.buffer_size
            
            # Get samples before write index
            if self.write_index >= samples_needed:
                return self.buffer[self.write_index - samples_needed:self.write_index].copy()
            else:
                # Wrap around to get samples
                part1 = self.buffer[self.write_index - samples_needed:]
                part2 = self.buffer[:self.write_index]
                return np.concatenate([part1, part2])


class WakeWordDetectionService:
    """Main service for wake word detection in standby mode."""
    
    def __init__(
        self,
        config: WakeWordConfig,
        stt_callback: Callable[[np.ndarray], str],
        wake_callback: Callable[[str, str], None]
    ):
        """
        Initialize wake word detection service.
        
        Args:
            config: Wake word configuration
            stt_callback: Function to transcribe audio to text
            wake_callback: Function called when wake word detected (wake_word, full_text)
        """
        self.config = config
        self.stt_callback = stt_callback
        self.wake_callback = wake_callback
        
        self.state = WakeWordState.IDLE
        self.detector = SimpleWakeWordDetector(config)
        self.audio_buffer = AudioBuffer(
            duration_seconds=config.context_seconds * 2,  # Keep double for safety
            sample_rate=config.sample_rate
        )
        
        self.audio_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.audio_thread = None
        self.processing_thread = None
        
        # Text buffer for accumulating transcriptions
        self.text_buffer = []
        self.text_buffer_lock = threading.Lock()
    
    def start(self):
        """Start wake word detection in standby mode."""
        if self.state != WakeWordState.IDLE:
            logger.warning(f"Cannot start from state {self.state}")
            return
        
        logger.info("Starting wake word detection service")
        self.state = WakeWordState.STANDBY
        self.stop_event.clear()
        
        # Start audio recording thread
        self.audio_thread = threading.Thread(target=self._audio_recording_loop)
        self.audio_thread.daemon = True
        self.audio_thread.start()
        
        # Start processing thread
        self.processing_thread = threading.Thread(target=self._audio_processing_loop)
        self.processing_thread.daemon = True
        self.processing_thread.start()
        
        logger.info(f"Wake word detection started, listening for: {self.config.wake_words}")
    
    def stop(self):
        """Stop wake word detection."""
        logger.info("Stopping wake word detection service")
        self.stop_event.set()
        
        if self.audio_thread:
            self.audio_thread.join(timeout=2.0)
        if self.processing_thread:
            self.processing_thread.join(timeout=2.0)
        
        self.state = WakeWordState.IDLE
        logger.info("Wake word detection stopped")
    
    def pause(self):
        """Pause detection (stand down command)."""
        if self.state == WakeWordState.STANDBY:
            self.state = WakeWordState.PAUSED
            logger.info("Wake word detection paused")
    
    def resume(self):
        """Resume detection."""
        if self.state == WakeWordState.PAUSED:
            self.state = WakeWordState.STANDBY
            logger.info("Wake word detection resumed")
    
    def _audio_recording_loop(self):
        """Continuous audio recording loop."""
        chunk_samples = int(self.config.chunk_duration * self.config.sample_rate)
        
        def audio_callback(indata, frames, time_info, status):
            if status:
                logger.warning(f"Audio recording status: {status}")
            if self.state in [WakeWordState.STANDBY, WakeWordState.PAUSED]:
                # Always record to buffer for context
                audio_chunk = indata[:, 0] if len(indata.shape) > 1 else indata
                self.audio_buffer.write(audio_chunk.copy())
                
                # Only process if in standby (not paused)
                if self.state == WakeWordState.STANDBY:
                    self.audio_queue.put(audio_chunk.copy())
        
        try:
            with sd.InputStream(
                samplerate=self.config.sample_rate,
                channels=1,
                callback=audio_callback,
                blocksize=chunk_samples
            ):
                while not self.stop_event.is_set():
                    time.sleep(0.1)
        except Exception as e:
            logger.error(f"Audio recording error: {e}")
    
    def _audio_processing_loop(self):
        """Process audio chunks for wake word detection."""
        accumulated_audio = []
        accumulated_samples = 0
        chunk_samples = int(self.config.chunk_duration * self.config.sample_rate)
        
        while not self.stop_event.is_set():
            try:
                # Get audio chunk with timeout
                audio_chunk = self.audio_queue.get(timeout=0.1)
                
                # Accumulate audio until we have enough for a chunk
                accumulated_audio.append(audio_chunk)
                accumulated_samples += len(audio_chunk)
                
                if accumulated_samples >= chunk_samples:
                    # Combine accumulated audio
                    full_audio = np.concatenate(accumulated_audio)
                    
                    # Take the chunk size we need
                    chunk_to_process = full_audio[:chunk_samples]
                    
                    # Keep any overflow for next chunk
                    if len(full_audio) > chunk_samples:
                        accumulated_audio = [full_audio[chunk_samples:]]
                        accumulated_samples = len(accumulated_audio[0])
                    else:
                        accumulated_audio = []
                        accumulated_samples = 0
                    
                    # Process the chunk
                    self._process_audio_chunk(chunk_to_process)
                    
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Audio processing error: {e}")
    
    def _process_audio_chunk(self, audio_chunk: np.ndarray):
        """Process a single audio chunk for wake word detection."""
        try:
            # Log chunk processing
            logger.debug(f"Processing audio chunk: {len(audio_chunk)} samples, max amplitude: {np.abs(audio_chunk).max():.4f}")
            
            # Transcribe audio using provided STT callback
            text = self.stt_callback(audio_chunk)
            
            if not text or text.strip() == "":
                logger.debug("No text from STT, continuing to listen...")
                return
            
            logger.info(f"Wake word detector received text: '{text}'")
            
            # Add to text buffer
            with self.text_buffer_lock:
                self.text_buffer.append({
                    'timestamp': time.time(),
                    'text': text
                })
                
                # Keep only recent text (last minute)
                cutoff_time = time.time() - 60
                self.text_buffer = [
                    item for item in self.text_buffer 
                    if item['timestamp'] > cutoff_time
                ]
            
            # Check for wake words or commands
            detection_result = self.detector.detect(text)
            
            if detection_result == "PAUSE":
                self.pause()
            elif detection_result == "RESUME":
                self.resume()
            elif detection_result and self.state == WakeWordState.STANDBY:
                # Wake word detected!
                logger.info(f"Wake word detected: {detection_result}")
                
                # Get context audio if requested
                context_audio = self.audio_buffer.get_last_n_seconds(
                    self.config.context_seconds
                )
                
                # Get recent text context
                with self.text_buffer_lock:
                    recent_text = " ".join([
                        item['text'] for item in self.text_buffer
                    ])
                
                # Notify via callback
                self.wake_callback(detection_result, recent_text)
                
        except Exception as e:
            logger.error(f"Error processing audio chunk: {e}")


# Environment variable integration
def get_wake_word_config() -> WakeWordConfig:
    """Load wake word configuration from environment variables."""
    config = WakeWordConfig()
    
    # Wake words
    wake_words_env = os.getenv("VOICE_MODE_WAKE_WORD", "Hey Claude")
    config.wake_words = [w.strip() for w in wake_words_env.split(",")]
    
    # Commands
    config.pause_command = os.getenv("VOICE_MODE_PAUSE_COMMAND", "stand down")
    config.resume_command = os.getenv("VOICE_MODE_RESUME_COMMAND", "standby")
    
    # Settings
    config.sensitivity = float(os.getenv("VOICE_MODE_WAKE_SENSITIVITY", "0.5"))
    config.context_seconds = float(os.getenv("VOICE_MODE_WAKE_CONTEXT_SECONDS", "10"))
    config.local_stt_only = os.getenv("VOICE_MODE_WAKE_LOCAL_ONLY", "true").lower() == "true"
    
    return config