"""Test wake word integration with converse tool."""

import pytest
from unittest.mock import Mock, patch, AsyncMock

# Test that converse accepts the wake word parameter
@pytest.mark.asyncio
async def test_converse_with_wake_word_parameter():
    """Test that converse function accepts wait_for_wake_word parameter."""
    # Import here to avoid circular imports
    from voice_mode.tools.conversation import converse
    
    # Mock the necessary dependencies
    with patch('voice_mode.tools.conversation.startup_initialization', new_callable=AsyncMock):
        with patch('voice_mode.tools.conversation.get_event_logger', return_value=None):
            # Test that the function accepts the parameter and returns expected message
            result = await converse(
                message="Test message",
                wait_for_response=False,
                wait_for_wake_word=True
            )
            
            assert "Wake word detection is not yet implemented" in result
            assert "coming soon" in result


@pytest.mark.asyncio 
async def test_converse_without_wake_word():
    """Test that converse works normally without wake word parameter."""
    from voice_mode.tools.conversation import converse
    
    # Mock dependencies
    with patch('voice_mode.tools.conversation.startup_initialization', new_callable=AsyncMock):
        with patch('voice_mode.tools.conversation.get_event_logger', return_value=None):
            with patch('voice_mode.tools.conversation.text_to_speech', new_callable=AsyncMock) as mock_tts:
                with patch('voice_mode.tools.conversation.get_tts_client_and_voice', new_callable=AsyncMock) as mock_get_client:
                    # Set up mock returns
                    mock_get_client.return_value = (
                        {'client': Mock(), 'base_url': 'http://test', 'model': 'test'},
                        'test-voice'
                    )
                    
                    # Test normal operation without wake word
                    result = await converse(
                        message="Hello world",
                        wait_for_response=False,
                        wait_for_wake_word=False
                    )
                    
                    # Should have called TTS
                    mock_tts.assert_called_once()
                    assert "Hello world" in str(mock_tts.call_args)