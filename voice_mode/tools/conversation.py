"""Conversation tools for interactive voice interactions."""

import asyncio
import logging
import os
import time
import traceback
import threading
from typing import Optional, Literal, Tuple, Dict
from pathlib import Path
from datetime import datetime

import numpy as np
import sounddevice as sd
from scipy.io.wavfile import write
from pydub import AudioSegment
from openai import AsyncOpenAI
import httpx

from voice_mode.wake_word import WakeWordDetectionService, get_wake_word_config

# Optional webrtcvad for silence detection
try:
    import webrtcvad
    VAD_AVAILABLE = True
    with open('/tmp/voicemode_vad_import.txt', 'w') as f:
        f.write(f"VAD import successful\n")
except ImportError as e:
    webrtcvad = None
    VAD_AVAILABLE = False
    with open('/tmp/voicemode_vad_import.txt', 'w') as f:
        f.write(f"VAD import failed: {e}\n")
        import sys
        f.write(f"Python path: {sys.path}\n")
        f.write(f"Python executable: {sys.executable}\n")

from voice_mode.server import mcp
from voice_mode.conversation_logger import get_conversation_logger
from voice_mode.config import (
    audio_operation_lock,
    SAMPLE_RATE,
    CHANNELS,
    DEBUG,
    DEBUG_DIR,
    SAVE_AUDIO,
    AUDIO_DIR,
    OPENAI_API_KEY,
    LIVEKIT_URL,
    LIVEKIT_API_KEY,
    LIVEKIT_API_SECRET,
    PREFER_LOCAL,
    AUDIO_FEEDBACK_ENABLED,
    service_processes,
    HTTP_CLIENT_CONFIG,
    save_transcription,
    SAVE_TRANSCRIPTIONS,
    DISABLE_SILENCE_DETECTION,
    VAD_AGGRESSIVENESS,
    SILENCE_THRESHOLD_MS,
    MIN_RECORDING_DURATION,
    VAD_CHUNK_DURATION_MS,
    INITIAL_SILENCE_GRACE_PERIOD
)
import voice_mode.config
from voice_mode.providers import (
    get_tts_client_and_voice,
    get_stt_client,
    is_provider_available,
    get_provider_by_voice,
    select_best_voice
)
from voice_mode.provider_discovery import provider_registry
from voice_mode.core import (
    get_openai_clients,
    text_to_speech,
    cleanup as cleanup_clients,
    save_debug_file,
    get_debug_filename,
    play_chime_start,
    play_chime_end
)
from voice_mode.tools.statistics import track_voice_interaction
from voice_mode.utils import (
    get_event_logger,
    log_recording_start,
    log_recording_end,
    log_stt_start,
    log_stt_complete,
    log_tool_request_start,
    log_tool_request_end
)

logger = logging.getLogger("voice-mode")

# Log silence detection config at module load time
logger.info(f"Module loaded with DISABLE_SILENCE_DETECTION={DISABLE_SILENCE_DETECTION}")

# Track last session end time for measuring AI thinking time
last_session_end_time = None

# Initialize OpenAI clients - now using provider registry for endpoint discovery
openai_clients = get_openai_clients(OPENAI_API_KEY or "dummy-key-for-local", None, None)

# Provider-specific clients are now created dynamically by the provider registry


async def startup_initialization():
    """Initialize services on startup based on configuration"""
    if voice_mode.config._startup_initialized:
        return
    
    voice_mode.config._startup_initialized = True
    logger.info("Running startup initialization...")
    
    # Initialize provider registry
    logger.info("Initializing provider registry...")
    await provider_registry.initialize()
    
    # Check if we should auto-start Kokoro
    auto_start_kokoro = os.getenv("VOICE_MODE_AUTO_START_KOKORO", "").lower() in ("true", "1", "yes", "on")
    if auto_start_kokoro:
        try:
            # Check if Kokoro is already running
            async with httpx.AsyncClient(timeout=3.0) as client:
                base_url = 'http://127.0.0.1:8880'  # Kokoro default
                health_url = f"{base_url}/health"
                response = await client.get(health_url)
                
                if response.status_code == 200:
                    logger.info("Kokoro TTS is already running externally")
                else:
                    raise Exception("Not running")
        except:
            # Kokoro is not running, start it
            logger.info("Auto-starting Kokoro TTS service...")
            try:
                # Import here to avoid circular dependency
                import subprocess
                if "kokoro" not in service_processes:
                    process = subprocess.Popen(
                        ["uvx", "kokoro-fastapi"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        env={**os.environ}
                    )
                    service_processes["kokoro"] = process
                    
                    # Wait a moment for it to start
                    await asyncio.sleep(2.0)
                    
                    # Verify it started
                    if process.poll() is None:
                        logger.info(f"✓ Kokoro TTS started successfully (PID: {process.pid})")
                    else:
                        logger.error("Failed to start Kokoro TTS")
            except Exception as e:
                logger.error(f"Error auto-starting Kokoro: {e}")
    
    # Log initial status
    logger.info("Service initialization complete")


async def get_tts_config(provider: Optional[str] = None, voice: Optional[str] = None, model: Optional[str] = None, instructions: Optional[str] = None):
    """Get TTS configuration based on provider selection"""
    logger.info(f"[DEBUG] get_tts_config called with provider={provider}, voice={voice}, model={model}")
    
    # Validate instructions usage
    if instructions and model != "gpt-4o-mini-tts":
        logger.warning(f"Instructions parameter is only supported with gpt-4o-mini-tts model, ignoring for model: {model}")
        instructions = None
    
    # Map provider names to base URLs
    provider_urls = {
        'openai': 'https://api.openai.com/v1',
        'kokoro': 'http://127.0.0.1:8880/v1'
    }
    
    # Convert provider name to URL if it's a known provider
    base_url = provider_urls.get(provider, provider)
    
    # Use new provider selection logic
    try:
        client, selected_voice, selected_model, endpoint_info = await get_tts_client_and_voice(
            voice=voice,
            model=model,
            base_url=base_url  # Now using mapped URL
        )
        
        # Return configuration compatible with existing code
        logger.info(f"[DEBUG] TTS endpoint selected: {endpoint_info.base_url} (provider: {endpoint_info.provider_type})")
        logger.info(f"[DEBUG] Using voice: {selected_voice}, model: {selected_model}")
        
        return {
            'client': client,
            'base_url': endpoint_info.base_url,
            'model': selected_model,
            'voice': selected_voice,
            'instructions': instructions,
            'provider': endpoint_info.base_url  # For logging
        }
    except Exception as e:
        logger.error(f"Failed to get TTS client: {e}")
        # Fallback to legacy behavior
        return {
            'client_key': 'tts',
            'base_url': 'https://api.openai.com/v1',  # Fallback to OpenAI
            'model': model or 'tts-1',
            'voice': voice or 'alloy',
            'instructions': instructions
        }


async def get_stt_config(provider: Optional[str] = None):
    """Get STT configuration based on provider selection"""
    try:
        # Use new provider selection logic
        client, selected_model, endpoint_info = await get_stt_client(
            model=None,  # Let system select
            base_url=provider  # Allow provider to be a base URL
        )
        
        return {
            'client': client,
            'base_url': endpoint_info.url,
            'model': selected_model,
            'provider': endpoint_info.url  # For logging
        }
    except Exception as e:
        logger.error(f"Failed to get STT client: {e}")
        # Fallback to legacy behavior
        return {
            'client_key': 'stt',
            'base_url': 'https://api.openai.com/v1',  # Fallback to OpenAI
            'model': 'whisper-1',
            'provider': 'openai-whisper'
        }



async def text_to_speech_with_failover(
    message: str,
    voice: Optional[str] = None,
    model: Optional[str] = None,
    instructions: Optional[str] = None,
    audio_format: Optional[str] = None,
    initial_provider: Optional[str] = None
) -> Tuple[bool, Optional[dict], Optional[dict]]:
    """
    Text to speech with automatic failover to next available endpoint.
    
    Returns:
        Tuple of (success, tts_metrics, tts_config)
    """
    from voice_mode.provider_discovery import provider_registry
    
    # Track which URLs we've tried
    tried_urls = set()
    last_error = None
    
    # If initial_provider specified, try it first
    if initial_provider:
        provider_urls = {'openai': 'https://api.openai.com/v1', 'kokoro': 'http://127.0.0.1:8880/v1'}
        initial_url = provider_urls.get(initial_provider, initial_provider)
        if initial_url:
            tried_urls.add(initial_url)
            try:
                tts_config = await get_tts_config(initial_provider, voice, model, instructions)
                
                # Handle both new client object and legacy client_key
                if 'client' in tts_config:
                    openai_clients['_temp_tts'] = tts_config['client']
                    client_key = '_temp_tts'
                else:
                    client_key = tts_config.get('client_key', 'tts')
                
                # Get conversation ID from logger
                conversation_logger = get_conversation_logger()
                conversation_id = conversation_logger.conversation_id
                
                success, tts_metrics = await text_to_speech(
                    text=message,
                    openai_clients=openai_clients,
                    tts_model=tts_config['model'],
                    tts_base_url=tts_config['base_url'],
                    tts_voice=tts_config['voice'],
                    debug=DEBUG,
                    debug_dir=DEBUG_DIR if DEBUG else None,
                    save_audio=SAVE_AUDIO,
                    audio_dir=AUDIO_DIR if SAVE_AUDIO else None,
                    client_key=client_key,
                    instructions=tts_config.get('instructions'),
                    audio_format=audio_format,
                    conversation_id=conversation_id
                )
                
                # Clean up temporary client
                if '_temp_tts' in openai_clients:
                    del openai_clients['_temp_tts']
                
                if success:
                    return success, tts_metrics, tts_config
                
                # Mark endpoint as unhealthy
                await provider_registry.mark_unhealthy('tts', tts_config['base_url'], 'TTS request failed')
                
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Initial provider {initial_provider} failed: {e}")
                logger.debug(f"Full error details for {initial_provider}:", exc_info=True)
    
    # Try remaining endpoints in order
    from voice_mode.config import TTS_BASE_URLS
    
    for base_url in TTS_BASE_URLS:
        if base_url in tried_urls:
            continue
            
        tried_urls.add(base_url)
        
        try:
            # Try to get config for this specific base URL
            tts_config = await get_tts_config(None, voice, model, instructions)
            
            # Skip if we got a different URL than requested (means our preferred wasn't available)
            if tts_config.get('base_url') != base_url:
                continue
            
            # Handle both new client object and legacy client_key
            if 'client' in tts_config:
                openai_clients['_temp_tts'] = tts_config['client']
                client_key = '_temp_tts'
            else:
                client_key = tts_config.get('client_key', 'tts')
            
            # Get conversation ID from logger
            conversation_logger = get_conversation_logger()
            conversation_id = conversation_logger.conversation_id
            
            success, tts_metrics = await text_to_speech(
                text=message,
                openai_clients=openai_clients,
                tts_model=tts_config['model'],
                tts_base_url=tts_config['base_url'],
                tts_voice=tts_config['voice'],
                debug=DEBUG,
                debug_dir=DEBUG_DIR if DEBUG else None,
                save_audio=SAVE_AUDIO,
                audio_dir=AUDIO_DIR if SAVE_AUDIO else None,
                client_key=client_key,
                instructions=tts_config.get('instructions'),
                audio_format=audio_format,
                conversation_id=conversation_id
            )
            
            # Clean up temporary client
            if '_temp_tts' in openai_clients:
                del openai_clients['_temp_tts']
            
            if success:
                logger.info(f"TTS succeeded with failover to: {base_url}")
                return success, tts_metrics, tts_config
            else:
                # Mark endpoint as unhealthy
                await provider_registry.mark_unhealthy('tts', base_url, 'TTS request failed')
                
        except Exception as e:
            last_error = str(e)
            logger.warning(f"TTS failed for {base_url}: {e}")
            # Mark endpoint as unhealthy
            await provider_registry.mark_unhealthy('tts', base_url, str(e))
    
    # All endpoints failed
    logger.error(f"All TTS endpoints failed. Last error: {last_error}")
    return False, None, None


async def speech_to_text(audio_data: np.ndarray, save_audio: bool = False, audio_dir: Optional[Path] = None) -> Optional[str]:
    """Convert audio to text with automatic failover"""
    # Use the new failover implementation
    return await speech_to_text_with_failover(audio_data, save_audio, audio_dir)


async def speech_to_text_with_failover(
    audio_data: np.ndarray, 
    save_audio: bool = False, 
    audio_dir: Optional[Path] = None
) -> Optional[str]:
    """
    Speech to text with automatic failover to next available endpoint.
    
    Returns:
        Transcribed text or None if all endpoints fail
    """
    from voice_mode.provider_discovery import provider_registry
    from voice_mode.config import STT_BASE_URLS
    
    # Track which URLs we've tried
    tried_urls = set()
    last_error = None
    
    # Try configured endpoints in order
    for base_url in STT_BASE_URLS:
        if base_url in tried_urls:
            continue
            
        tried_urls.add(base_url)
        
        try:
            # Get STT config for this specific endpoint
            client, selected_model, endpoint_info = await get_stt_client(base_url=base_url)
            
            if not client:
                logger.warning(f"No STT client available for {base_url}")
                continue
            
            stt_config = {
                'client': client,
                'model': selected_model,
                'base_url': endpoint_info.base_url if endpoint_info else base_url,
                'provider': 'whisper-local' if '127.0.0.1' in base_url or '127.0.0.1' in base_url else 'openai-whisper'
            }
            
            logger.info(f"Attempting STT with {stt_config['provider']} at {stt_config['base_url']}")
            
            # Create openai_clients dict with temporary STT client
            openai_clients = {'_temp_stt': client}
            
            # Call original speech_to_text with this config
            result = await _speech_to_text_internal(
                audio_data, 
                stt_config, 
                openai_clients,
                save_audio, 
                audio_dir
            )
            
            if result:
                logger.info(f"STT succeeded with {stt_config['provider']}")
                return result
            else:
                # Don't mark as unhealthy - silence is a valid result
                logger.debug(f"STT returned no result (possibly silent audio) for {stt_config['provider']}")
                
        except Exception as e:
            last_error = str(e)
            logger.warning(f"STT failed for {base_url}: {e}")
            # Mark endpoint as unhealthy
            await provider_registry.mark_unhealthy('stt', base_url, str(e))
    
    # All endpoints failed or returned no result
    if last_error:
        logger.error(f"All STT endpoints failed. Last error: {last_error}")
    else:
        logger.debug("All STT endpoints returned no result (possibly silent audio)")
    return None


async def _speech_to_text_internal(
    audio_data: np.ndarray,
    stt_config: dict,
    openai_clients: dict,
    save_audio: bool = False,
    audio_dir: Optional[Path] = None
) -> Optional[str]:
    """Internal speech to text implementation (extracted from original speech_to_text)"""
    logger.info(f"STT: Converting speech to text, audio data shape: {audio_data.shape}")
    
    if DEBUG:
        logger.debug(f"STT config - Model: {stt_config['model']}, Base URL: {stt_config['base_url']}")
        logger.debug(f"Audio stats - Min: {audio_data.min()}, Max: {audio_data.max()}, Mean: {audio_data.mean():.2f}")
    
    wav_file = None
    export_file = None
    export_format = None
    audio_path = None
    duration = len(audio_data) / SAMPLE_RATE  # Calculate duration using global SAMPLE_RATE
    try:
        import tempfile
        
        # Check if input is silent
        if np.abs(audio_data).max() < 0.001:
            logger.debug("Audio appears to be silent")
            return None
        
        # Ensure audio is in the correct format
        if audio_data.dtype != np.int16:
            logger.debug(f"Converting audio from {audio_data.dtype} to int16")
            audio_data = (audio_data * 32767).astype(np.int16)
        
        # Save as WAV file temporarily
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as wav_file_obj:
            wav_file = wav_file_obj.name
            logger.debug(f"Writing audio to WAV file: {wav_file}")
            write(wav_file, SAMPLE_RATE, audio_data)
        
        # Save debug file for original recording
        if DEBUG:
            try:
                with open(wav_file, 'rb') as f:
                    debug_path = save_debug_file(f.read(), "stt-input", "wav", DEBUG_DIR, DEBUG)
                    if debug_path:
                        logger.info(f"STT debug recording saved to: {debug_path}")
            except Exception as e:
                logger.error(f"Failed to save debug WAV: {e}")
        
        # Save audio file if audio saving is enabled
        if save_audio and audio_dir:
            try:
                with open(wav_file, 'rb') as f:
                    # Get conversation ID from logger
                    conversation_logger = get_conversation_logger()
                    conversation_id = conversation_logger.conversation_id
                    audio_path = save_debug_file(f.read(), "stt", "wav", audio_dir, True, conversation_id)
                    if audio_path:
                        logger.info(f"STT audio saved to: {audio_path}")
            except Exception as e:
                logger.error(f"Failed to save audio WAV: {e}")
        
        # Import config for audio format
        from ..config import STT_AUDIO_FORMAT, validate_audio_format, get_format_export_params
        
        # Determine provider from base URL (simple heuristic)
        provider = stt_config.get('provider', 'openai-whisper')
        # Check if using local Whisper endpoint
        if stt_config.get('base_url') and ("127.0.0.1" in stt_config['base_url'] or "127.0.0.1" in stt_config['base_url']):
            provider = "whisper-local"
        
        # Validate format for provider
        export_format = validate_audio_format(STT_AUDIO_FORMAT, provider, "stt")
        
        # Convert WAV to target format for upload
        logger.debug(f"Converting WAV to {export_format.upper()} for upload...")
        try:
            audio = AudioSegment.from_wav(wav_file)
            logger.debug(f"Audio loaded - Duration: {len(audio)}ms, Channels: {audio.channels}, Frame rate: {audio.frame_rate}")
            
            # Get export parameters for the format
            export_params = get_format_export_params(export_format)
            
            with tempfile.NamedTemporaryFile(suffix=f'.{export_format}', delete=False) as export_file_obj:
                export_file = export_file_obj.name
                audio.export(export_file, **export_params)
                upload_file = export_file
                logger.debug(f"{export_format.upper()} created for STT upload: {upload_file}")
        except Exception as e:
            if "ffmpeg" in str(e).lower() or "avconv" in str(e).lower():
                logger.error(f"Audio conversion failed - FFmpeg may not be installed: {e}")
                from voice_mode.utils.ffmpeg_check import get_install_instructions
                logger.error(f"\n{get_install_instructions()}")
                raise RuntimeError("FFmpeg is required but not found. Please install FFmpeg and try again.") from e
            else:
                raise
        
        # Save debug file for upload version
        if DEBUG:
            try:
                with open(upload_file, 'rb') as f:
                    debug_path = save_debug_file(f.read(), "stt-upload", export_format, DEBUG_DIR, DEBUG)
                    if debug_path:
                        logger.info(f"Upload audio saved to: {debug_path}")
            except Exception as e:
                logger.error(f"Failed to save debug {export_format.upper()}: {e}")
        
        # Get file size for logging
        file_size = os.path.getsize(upload_file)
        logger.debug(f"Uploading {file_size} bytes to STT API...")
        
        # Perform STT based on configuration
        with open(upload_file, 'rb') as audio_file:
            # Use client from config
            if 'client' in stt_config:
                stt_client = stt_config['client']
            else:
                # Legacy: get from openai_clients dict
                client_key = stt_config.get('client_key', 'stt')
                stt_client = openai_clients.get(client_key)
                if not stt_client:
                    # Fallback to temporary client
                    stt_client = openai_clients['_temp_stt']
            
            transcription = await stt_client.audio.transcriptions.create(
                model=stt_config['model'],
                file=audio_file,
                response_format="text"
            )
            
            logger.debug(f"STT API response type: {type(transcription)}")
            text = transcription.strip() if isinstance(transcription, str) else transcription.text.strip()
            
            if text:
                logger.info(f"✓ STT result: '{text}'")
                
                # Save transcription if enabled
                if SAVE_TRANSCRIPTIONS:
                    metadata = {
                        "type": "stt",
                        "model": stt_config.get('model', 'unknown'),
                        "provider": stt_config.get('provider', 'unknown'),
                        "timestamp": datetime.now().isoformat()
                    }
                    save_transcription(text, prefix="stt", metadata=metadata)
                
                # Log to JSONL
                try:
                    conversation_logger = get_conversation_logger()
                    conversation_logger.log_stt(
                        text=text,
                        audio_file=os.path.basename(audio_path) if audio_path else None,
                        duration_ms=int(duration * 1000) if duration else None,
                        model=stt_config.get('model'),
                        provider=stt_config.get('provider', 'openai'),
                        audio_format='mp3'  # STT uploads are always mp3
                    )
                except Exception as e:
                    logger.error(f"Failed to log STT to JSONL: {e}")
                
                return text
            else:
                logger.warning("STT returned empty text")
                return None
                    
    except Exception as e:
        logger.error(f"STT failed: {e}")
        logger.error(f"STT config when error occurred - Model: {stt_config.get('model', 'unknown')}, Base URL: {stt_config.get('base_url', 'unknown')}")
        
        # Check for authentication errors
        error_message = str(e).lower()
        base_url = stt_config.get('base_url', '')
        if hasattr(e, 'response'):
            logger.error(f"HTTP status: {e.response.status_code if hasattr(e.response, 'status_code') else 'unknown'}")
            logger.error(f"Response text: {e.response.text if hasattr(e.response, 'text') else 'unknown'}")
            
            # Check for 401 Unauthorized specifically on OpenAI endpoints
            if hasattr(e.response, 'status_code') and e.response.status_code == 401:
                if 'openai.com' in base_url:
                    logger.error("⚠️  Authentication failed with OpenAI. Please set OPENAI_API_KEY environment variable.")
                    logger.error("   Alternatively, you can use local services (Whisper) without an API key.")
        elif 'api key' in error_message or 'unauthorized' in error_message or 'authentication' in error_message:
            if 'openai.com' in base_url:
                logger.error("⚠️  Authentication issue detected. Please check your OPENAI_API_KEY.")
                logger.error("   For local-only usage, ensure Whisper is running and configured.")
        
        return None
    finally:
        # Clean up temporary files
        if wav_file and os.path.exists(wav_file):
            try:
                os.unlink(wav_file)
                logger.debug(f"Cleaned up WAV file: {wav_file}")
            except Exception as e:
                logger.error(f"Failed to clean up WAV file: {e}")
        
        if export_file and os.path.exists(export_file):
            try:
                os.unlink(export_file)
                export_format = export_format if 'export_format' in locals() else 'audio'
                logger.debug(f"Cleaned up {export_format.upper()} file: {export_file}")
            except Exception as e:
                logger.error(f"Failed to clean up {export_format.upper() if 'export_format' in locals() else 'audio'} file: {e}")


async def play_audio_feedback(
    text: str, 
    openai_clients: dict, 
    enabled: Optional[bool] = None, 
    style: str = "whisper", 
    feedback_type: Optional[str] = None,
    voice: str = "nova",
    model: str = "gpt-4o-mini-tts"
) -> None:
    """Play an audio feedback chime
    
    Args:
        text: Which chime to play (either "listening" or "finished")
        openai_clients: OpenAI client instances (kept for compatibility, not used)
        enabled: Override global audio feedback setting
        style: Kept for compatibility, not used
        feedback_type: Kept for compatibility, not used
        voice: Kept for compatibility, not used
        model: Kept for compatibility, not used
    """
    # Use parameter override if provided, otherwise use global setting
    if enabled is False:
        return
    
    # If enabled is None, use global setting
    if enabled is None:
        enabled = AUDIO_FEEDBACK_ENABLED
    
    # Skip if disabled
    if not enabled:
        return
    
    try:
        # Play appropriate chime
        if text == "listening":
            await play_chime_start()
        elif text == "finished":
            await play_chime_end()
    except Exception as e:
        logger.debug(f"Audio feedback failed: {e}")
        # Don't interrupt the main flow if feedback fails


def record_audio(duration: float) -> np.ndarray:
    """Record audio from microphone"""
    logger.info(f"🎤 Recording audio for {duration}s...")
    if DEBUG:
        try:
            devices = sd.query_devices()
            default_input = sd.default.device[0]
            logger.debug(f"Default input device: {default_input} - {devices[default_input]['name'] if default_input is not None else 'None'}")
            logger.debug(f"Recording config - Sample rate: {SAMPLE_RATE}Hz, Channels: {CHANNELS}, dtype: int16")
        except Exception as dev_e:
            logger.error(f"Error querying audio devices: {dev_e}")
    
    # Save current stdio state
    import sys
    original_stdin = sys.stdin
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    
    try:
        samples_to_record = int(duration * SAMPLE_RATE)
        logger.debug(f"Recording {samples_to_record} samples...")
        
        recording = sd.rec(
            samples_to_record,
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=np.int16
        )
        sd.wait()
        
        flattened = recording.flatten()
        logger.info(f"✓ Recorded {len(flattened)} samples")
        
        if DEBUG:
            logger.debug(f"Recording stats - Min: {flattened.min()}, Max: {flattened.max()}, Mean: {flattened.mean():.2f}")
            # Check if recording contains actual audio (not silence)
            rms = np.sqrt(np.mean(flattened.astype(float) ** 2))
            logger.debug(f"RMS level: {rms:.2f} ({'likely silence' if rms < 100 else 'audio detected'})")
        
        return flattened
        
    except Exception as e:
        logger.error(f"Recording failed: {e}")
        logger.error(f"Audio config when error occurred - Sample rate: {SAMPLE_RATE}, Channels: {CHANNELS}")
        
        # Import here to avoid circular imports
        from voice_mode.utils.audio_diagnostics import get_audio_error_help
        
        # Get helpful error message
        help_message = get_audio_error_help(e)
        logger.error(f"\n{help_message}")
        
        # Try to get more info about audio devices
        try:
            devices = sd.query_devices()
            logger.error(f"Available input devices:")
            for i, device in enumerate(devices):
                if device['max_input_channels'] > 0:
                    logger.error(f"  {i}: {device['name']} (inputs: {device['max_input_channels']})")
        except Exception as dev_e:
            logger.error(f"Cannot query audio devices: {dev_e}")
        
        return np.array([])
    finally:
        # Restore stdio if it was changed
        if sys.stdin != original_stdin:
            sys.stdin = original_stdin
        if sys.stdout != original_stdout:
            sys.stdout = original_stdout
        if sys.stderr != original_stderr:
            sys.stderr = original_stderr


def record_audio_with_silence_detection(max_duration: float, disable_silence_detection: bool = False, min_duration: float = 0.0) -> np.ndarray:
    """Record audio from microphone with automatic silence detection.
    
    Uses WebRTC VAD to detect when the user stops speaking and automatically
    stops recording after a configurable silence threshold.
    
    Args:
        max_duration: Maximum recording duration in seconds
        disable_silence_detection: If True, disables silence detection and uses fixed duration recording
        min_duration: Minimum recording duration before silence detection can stop (default: 0.0)
        
    Returns:
        Numpy array of recorded audio samples
    """
    # Write to file for debugging
    with open('/tmp/voicemode_silence_debug.txt', 'a') as f:
        f.write(f"[{time.time()}] record_audio_with_silence_detection called - VAD={VAD_AVAILABLE}, DISABLED={DISABLE_SILENCE_DETECTION}\n")
        f.flush()
    
    logger.info(f"record_audio_with_silence_detection called - VAD_AVAILABLE={VAD_AVAILABLE}, DISABLE_SILENCE_DETECTION={DISABLE_SILENCE_DETECTION}, min_duration={min_duration}")
    
    if not VAD_AVAILABLE:
        logger.warning("webrtcvad not available, falling back to fixed duration recording")
        return record_audio(max_duration)
    
    if DISABLE_SILENCE_DETECTION or disable_silence_detection:
        if disable_silence_detection:
            logger.info("Silence detection disabled for this interaction by request")
        else:
            logger.info("Silence detection disabled globally via VOICEMODE_DISABLE_SILENCE_DETECTION")
        return record_audio(max_duration)
    
    logger.info(f"🎤 Recording with silence detection (max {max_duration}s)...")
    
    try:
        # Initialize VAD
        vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)
        
        # Calculate chunk size (must be 10, 20, or 30ms worth of samples)
        chunk_samples = int(SAMPLE_RATE * VAD_CHUNK_DURATION_MS / 1000)
        chunk_duration_s = VAD_CHUNK_DURATION_MS / 1000
        
        # WebRTC VAD only supports 8000, 16000, or 32000 Hz
        # We'll tell VAD we're using 16kHz even though we're recording at 24kHz
        # This requires adjusting our chunk size to match what VAD expects
        vad_sample_rate = 16000
        vad_chunk_samples = int(vad_sample_rate * VAD_CHUNK_DURATION_MS / 1000)
        
        # Recording state
        chunks = []
        silence_duration_ms = 0
        recording_duration = 0
        speech_detected = False
        stop_recording = False
        
        # Use a queue for thread-safe communication
        import queue
        audio_queue = queue.Queue()
        
        # Save stdio state
        import sys
        original_stdin = sys.stdin
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        
        logger.debug(f"VAD config - Aggressiveness: {VAD_AGGRESSIVENESS}, "
                    f"Silence threshold: {SILENCE_THRESHOLD_MS}ms, "
                    f"Min duration: {MIN_RECORDING_DURATION}s, "
                    f"Initial grace period: {INITIAL_SILENCE_GRACE_PERIOD}s")
        
        def audio_callback(indata, frames, time, status):
            """Callback for continuous audio stream"""
            if status:
                logger.warning(f"Audio stream status: {status}")
            # Put the audio data in the queue for processing
            audio_queue.put(indata.copy())
        
        try:
            # Create continuous input stream
            with sd.InputStream(samplerate=SAMPLE_RATE,
                               channels=CHANNELS,
                               dtype=np.int16,
                               callback=audio_callback,
                               blocksize=chunk_samples):
                
                logger.debug("Started continuous audio stream")
                
                while recording_duration < max_duration and not stop_recording:
                    try:
                        # Get audio chunk from queue with timeout
                        chunk = audio_queue.get(timeout=0.1)
                        
                        # Flatten for consistency
                        chunk_flat = chunk.flatten()
                        chunks.append(chunk_flat)
                        
                        # For VAD, we need to provide exactly the right number of bytes
                        # VAD expects 16kHz audio, so we'll take a subset of our 24kHz samples
                        # This is a simple downsampling approach that works for VAD
                        vad_chunk = chunk_flat[:vad_chunk_samples]
                        chunk_bytes = vad_chunk.tobytes()
                        
                        # Check if chunk contains speech
                        try:
                            is_speech = vad.is_speech(chunk_bytes, vad_sample_rate)
                        except Exception as vad_e:
                            logger.warning(f"VAD error: {vad_e}, treating as speech")
                            is_speech = True
                        
                        if is_speech:
                            if not speech_detected:
                                logger.debug("Speech detected, recording...")
                            speech_detected = True
                            silence_duration_ms = 0
                        else:
                            silence_duration_ms += VAD_CHUNK_DURATION_MS
                            if speech_detected and silence_duration_ms % 200 == 0:  # Log every 200ms
                                logger.debug(f"Silence: {silence_duration_ms}ms")
                        
                        recording_duration += chunk_duration_s
                        
                        # Check stop conditions
                        # Use the larger of MIN_RECORDING_DURATION (global) or min_duration (parameter)
                        effective_min_duration = max(MIN_RECORDING_DURATION, min_duration)
                        if speech_detected and recording_duration >= effective_min_duration:
                            if silence_duration_ms >= SILENCE_THRESHOLD_MS:
                                logger.info(f"✓ Silence detected after {recording_duration:.1f}s (min: {effective_min_duration:.1f}s), stopping recording")
                                stop_recording = True
                        
                        # Also stop if we haven't detected any speech after a grace period
                        # Give user time to start speaking
                        if not speech_detected and recording_duration >= INITIAL_SILENCE_GRACE_PERIOD:
                            logger.info(f"No speech detected after {INITIAL_SILENCE_GRACE_PERIOD}s grace period, stopping recording")
                            stop_recording = True
                            
                    except queue.Empty:
                        # No audio data available, continue waiting
                        continue
                    except Exception as e:
                        logger.error(f"Error processing audio chunk: {e}")
                        break
            
            # Concatenate all chunks
            if chunks:
                full_recording = np.concatenate(chunks)
                logger.info(f"✓ Recorded {len(full_recording)} samples ({recording_duration:.1f}s)")
                
                if DEBUG:
                    # Calculate RMS for debug
                    rms = np.sqrt(np.mean(full_recording.astype(float) ** 2))
                    logger.debug(f"Recording stats - RMS: {rms:.2f}, Speech detected: {speech_detected}")
                
                return full_recording
            else:
                logger.warning("No audio chunks recorded")
                return np.array([])
                
        except Exception as e:
            logger.error(f"Recording with VAD failed: {e}")
            
            # Import here to avoid circular imports
            from voice_mode.utils.audio_diagnostics import get_audio_error_help
            
            # Get helpful error message
            help_message = get_audio_error_help(e)
            logger.error(f"\n{help_message}")
            
            logger.info("Falling back to fixed duration recording")
            return record_audio(max_duration)
            
        finally:
            # Restore stdio
            if sys.stdin != original_stdin:
                sys.stdin = original_stdin
            if sys.stdout != original_stdout:
                sys.stdout = original_stdout
            if sys.stderr != original_stderr:
                sys.stderr = original_stderr
    
    except Exception as e:
        logger.error(f"VAD initialization failed: {e}")
        logger.info("Falling back to fixed duration recording")
        return record_audio(max_duration)


async def check_livekit_available() -> bool:
    """Check if LiveKit is available and has active rooms"""
    try:
        from livekit import api
        
        api_url = LIVEKIT_URL.replace("ws://", "http://").replace("wss://", "https://")
        lk_api = api.LiveKitAPI(api_url, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        
        rooms = await lk_api.room.list_rooms(api.ListRoomsRequest())
        active_rooms = [r for r in rooms.rooms if r.num_participants > 0]
        
        return len(active_rooms) > 0
        
    except Exception as e:
        logger.debug(f"LiveKit not available: {e}")
        return False


async def livekit_converse(message: str, room_name: str = "", timeout: float = 60.0) -> str:
    """Have a conversation using LiveKit transport"""
    try:
        from livekit import rtc, api
        from livekit.agents import Agent, AgentSession
        from livekit.plugins import openai as lk_openai, silero
        
        # Auto-discover room if needed
        if not room_name:
            api_url = LIVEKIT_URL.replace("ws://", "http://").replace("wss://", "https://")
            lk_api = api.LiveKitAPI(api_url, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
            
            rooms = await lk_api.room.list_rooms(api.ListRoomsRequest())
            for room in rooms.rooms:
                if room.num_participants > 0:
                    room_name = room.name
                    break
            
            if not room_name:
                return "No active LiveKit rooms found"
        
        # Setup TTS and STT for LiveKit
        # Get default providers from registry
        tts_config = await get_tts_config()
        stt_config = await get_stt_config()
        tts_client = lk_openai.TTS(voice=tts_config['voice'], base_url=tts_config['base_url'], model=tts_config['model'])
        stt_client = lk_openai.STT(base_url=stt_config['base_url'], model=stt_config['model'])
        
        # Create simple agent that speaks and listens
        class VoiceAgent(Agent):
            def __init__(self):
                super().__init__(
                    instructions="Speak the message and listen for response",
                    stt=stt_client,
                    tts=tts_client,
                    llm=None
                )
                self.response = None
                self.has_spoken = False
                self.speech_start_time = None
                self.min_speech_duration = 3.0  # Minimum 3 seconds of speech
            
            async def on_enter(self):
                await asyncio.sleep(0.5)
                if self.session:
                    await self.session.say(message, allow_interruptions=True)
                    self.has_spoken = True
            
            async def on_user_speech_started(self):
                """Track when user starts speaking"""
                self.speech_start_time = time.time()
                logger.debug("User started speaking")
            
            async def on_user_turn_completed(self, chat_ctx, new_message):
                if self.has_spoken and not self.response and new_message.content:
                    content = new_message.content[0]
                    
                    # Check if speech duration was long enough
                    if self.speech_start_time:
                        speech_duration = time.time() - self.speech_start_time
                        if speech_duration < self.min_speech_duration:
                            logger.debug(f"Speech too short ({speech_duration:.1f}s < {self.min_speech_duration}s), ignoring")
                            return
                    
                    # Filter out common ASR hallucinations
                    content_lower = content.lower().strip()
                    if content_lower in ['bye', 'bye.', 'goodbye', 'goodbye.', '...', 'um', 'uh', 'hmm', 'hm']:
                        logger.debug(f"Filtered out ASR hallucination: '{content}'")
                        return
                    
                    # Check if we have actual words (not just punctuation or numbers)
                    words = content.split()
                    has_real_words = any(word.isalpha() and len(word) > 1 for word in words)
                    if not has_real_words:
                        logger.debug(f"No real words detected in: '{content}'")
                        return
                    
                    # Filter out excessive repetitions (e.g., "45, 45, 45, 45...")
                    if len(words) > 5:
                        # Check if last 5 words are all the same
                        last_words = words[-5:]
                        if len(set(last_words)) == 1:
                            # Trim repetitive ending
                            content = ' '.join(words[:-4])
                            logger.debug(f"Trimmed repetitive ending from ASR output")
                    
                    # Ensure we have meaningful content
                    if content.strip() and len(content.strip()) > 2:
                        self.response = content
                        logger.debug(f"Accepted response: '{content}'")
        
        # Connect and run
        token = api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        token.with_identity("voice-mode-bot").with_name("Voice Mode Bot")
        token.with_grants(api.VideoGrants(
            room_join=True, room=room_name,
            can_publish=True, can_subscribe=True,
        ))
        
        room = rtc.Room()
        await room.connect(LIVEKIT_URL, token.to_jwt())
        
        if not room.remote_participants:
            await room.disconnect()
            return "No participants in LiveKit room"
        
        agent = VoiceAgent()
        # Configure Silero VAD with less aggressive settings for better end-of-turn detection
        vad = silero.VAD.load(
            min_speech_duration=0.1,        # Slightly increased - require more speech to start
            min_silence_duration=1.2,       # Increased to 1.2s - wait much longer before ending speech
            prefix_padding_duration=0.5,    # Keep default - padding at speech start
            max_buffered_speech=60.0,       # Keep default - max speech buffer
            activation_threshold=0.35,      # Lowered to 0.35 - more sensitive to soft speech
            sample_rate=16000,              # Standard sample rate
            force_cpu=True                  # Use CPU for compatibility
        )
        session = AgentSession(vad=vad)
        await session.start(room=room, agent=agent)
        
        # Wait for response
        start_time = time.time()
        while time.time() - start_time < timeout:
            if agent.response:
                await room.disconnect()
                return agent.response
            await asyncio.sleep(0.1)
        
        await room.disconnect()
        return f"No response within {timeout}s"
        
    except Exception as e:
        logger.error(f"LiveKit error: {e}")
        return f"LiveKit error: {str(e)}"


@mcp.tool()
async def converse(
    message: str,
    wait_for_response: bool = True,
    listen_duration: float = 30.0,
    min_listen_duration: float = 2.0,
    transport: Literal["auto", "local", "livekit"] = "auto",
    room_name: str = "",
    timeout: float = 60.0,
    voice: Optional[str] = None,
    tts_provider: Optional[Literal["openai", "kokoro"]] = None,
    tts_model: Optional[str] = None,
    tts_instructions: Optional[str] = None,
    audio_feedback: Optional[bool] = None,
    audio_feedback_style: Optional[str] = None,
    audio_format: Optional[str] = None,
    disable_silence_detection: bool = False,
    wait_for_wake_word: bool = False
) -> str:
    """Have a voice conversation - speak a message and optionally listen for response.
    
    🌍 LANGUAGE SUPPORT - ALWAYS SELECT APPROPRIATE VOICE FOR NON-ENGLISH TEXT:
    When speaking non-English languages, you MUST specify the appropriate voice and provider:
    - Spanish: voice="ef_dora" (or "em_alex"), tts_provider="kokoro"
    - French: voice="ff_siwis", tts_provider="kokoro"
    - Italian: voice="if_sara" (or "im_nicola"), tts_provider="kokoro"
    - Portuguese: voice="pf_dora" (or "pm_alex"), tts_provider="kokoro"
    - Chinese: voice="zf_xiaobei" (female) or "zm_yunjian" (male), tts_provider="kokoro"
    - Japanese: voice="jf_alpha" (female) or "jm_kumo" (male), tts_provider="kokoro"
    - Hindi: voice="hf_alpha" (female) or "hm_omega" (male), tts_provider="kokoro"
    
    ⚠️ IMPORTANT: Default voices (OpenAI) will speak non-English text with an American accent.
    Always check the message content and select language-appropriate voices for natural pronunciation.
    
    PRIVACY NOTICE: When wait_for_response is True, this tool will access your microphone
    to record audio for speech-to-text conversion. Audio is processed using the configured
    STT service and is not permanently stored. Do not use upper case except for acronyms as the TTS will spell these out.
    
    Args:
        message: The message to speak
        wait_for_response: Whether to listen for a response after speaking (default: True)
        listen_duration: How long to listen for response in seconds (default: 30.0)
                         Recommended durations based on expected response:
                         - Simple yes/no questions: 10 seconds
                         - Normal conversational responses: 20 seconds  
                         - Open-ended questions: 30 seconds (default)
                         - Detailed explanations: 45 seconds
                         - Stories or long explanations: 60 seconds
                         Always err on the side of longer duration - it's better to have 
                         silence at the end than to cut off the user mid-sentence.
        min_listen_duration: Minimum time to record before silence detection can stop (default: 2.0)
                             Useful for preventing premature cutoffs when users need thinking time.
                             Examples:
                             - Complex questions: 2-3 seconds
                             - Open-ended prompts: 3-5 seconds  
                             - Quick responses: 0.5-1 second
        transport: Transport method - "auto" (try LiveKit then local), "local" (direct mic), "livekit" (room-based)
        room_name: LiveKit room name (only for livekit transport, auto-discovered if empty)
        timeout: Maximum wait time for response in seconds (LiveKit only)
        voice: Override TTS voice - ONLY specify if user explicitly requests a specific voice
               OR when speaking non-English languages (see LANGUAGE SUPPORT section above).
               Examples: nova, shimmer (OpenAI); af_sky, af_sarah, am_adam (Kokoro)
               IMPORTANT: Never use 'coral' voice.
        tts_provider: TTS provider - ONLY specify if user explicitly requests or for failover testing
                      The system automatically selects based on availability and preferences.
        tts_model: TTS model - ONLY specify for specific features (e.g., gpt-4o-mini-tts for emotions)
                   The system automatically selects the best available model.
                   Options: tts-1, tts-1-hd, gpt-4o-mini-tts (OpenAI); Kokoro uses tts-1
        tts_instructions: Tone/style instructions for gpt-4o-mini-tts model only (e.g., "Speak in a cheerful tone", "Sound angry", "Be extremely sad")
        audio_feedback: Override global audio feedback setting (default: None uses VOICE_MODE_AUDIO_FEEDBACK env var)
        audio_feedback_style: Audio feedback style - "whisper" (default) or "shout" (default: None uses VOICE_MODE_FEEDBACK_STYLE env var)
        audio_format: Override audio format (pcm, mp3, wav, flac, aac, opus) - defaults to VOICEMODE_TTS_AUDIO_FORMAT env var
        disable_silence_detection: Disable silence detection for this interaction only (default: False)
                                   Silence detection automatically stops recording after detecting silence. 
                                   Disable if user reports being cut off, in noisy environments, or for 
                                   use cases like dictation where pauses are expected.
        wait_for_wake_word: If True, enter standby mode and wait for wake word before processing (default: False)
                            This enables hands-free operation by listening for "Hey Claude" or configured wake word.
        If wait_for_response is False: Confirmation that message was spoken
        If wait_for_response is True: The voice response received (or error/timeout message)
    
    Examples:
        - Ask a question: converse("What's your name?")  # Let system auto-select voice/model
        - Make a statement and wait: converse("Tell me more about that")  # Auto-selection recommended
        - Just speak without waiting: converse("Goodbye!", wait_for_response=False)
        - User requests specific voice: converse("Hello", voice="nova")  # Only when explicitly requested
        - Need HD quality: converse("High quality speech", tts_model="tts-1-hd")  # Only for specific features
        
    Language-Specific Examples (MUST specify voice & provider):
        - Spanish: converse("¿Cómo estás?", voice="ef_dora", tts_provider="kokoro")
        - French: converse("Bonjour!", voice="ff_siwis", tts_provider="kokoro")
        - Italian: converse("Ciao!", voice="if_sara", tts_provider="kokoro")
        - Chinese: converse("你好", voice="zf_xiaobei", tts_provider="kokoro")
        
    Emotional Speech (Requires OpenAI API):
        - Excitement: converse("We did it!", tts_model="gpt-4o-mini-tts", tts_instructions="Sound extremely excited and celebratory")
        - Sadness: converse("I'm sorry for your loss", tts_model="gpt-4o-mini-tts", tts_instructions="Sound gentle and sympathetic")
        - Urgency: converse("Watch out!", tts_model="gpt-4o-mini-tts", tts_instructions="Sound urgent and concerned")
        - Humor: converse("That's hilarious!", tts_model="gpt-4o-mini-tts", tts_instructions="Sound amused and playful")
        
    Note: Emotional speech uses OpenAI's gpt-4o-mini-tts model and incurs API costs (~$0.02/minute)
    """
    logger.info(f"Converse: '{message[:50]}{'...' if len(message) > 50 else ''}' (wait_for_response: {wait_for_response})")
    
    # Handle wake word detection mode
    if wait_for_wake_word:
        logger.info("Entering standby mode for wake word detection")
        
        try:
            # Get wake word configuration
            wake_config = get_wake_word_config()
            
            # Check if we should return to standby mode after conversation
            return_to_standby = os.getenv("VOICE_MODE_STANDBY", "off").lower() == "on"
            
            # Announce standby mode using TTS
            standby_message = f"Standing by for '{wake_config.wake_words[0]}'..."
            
            # For now, just log the message until TTS is properly integrated
            logger.info(f"Wake word mode: {standby_message}")
            print(f"\n🎤 {standby_message}\n")
            
            # Create STT callback that uses local Whisper only
            def stt_callback_sync(audio_chunk: np.ndarray) -> str:
                """Synchronous STT callback for wake word detection."""
                try:
                    # Log audio chunk info
                    logger.info(f"Wake word STT: Processing {len(audio_chunk)} samples ({len(audio_chunk)/wake_config.sample_rate:.1f}s)")
                    
                    # Check for silence
                    audio_max = np.abs(audio_chunk).max()
                    if audio_max < 0.001:
                        logger.debug("Wake word STT: Audio chunk is silent, skipping STT")
                        return ""
                    
                    # Run async operations in sync context
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        if wake_config.local_stt_only:
                            # Only use local STT (Whisper)
                            logger.info("Wake word STT: Using local-only mode")
                            
                            # Get local STT client specifically
                            local_url = 'http://127.0.0.1:2022/v1'
                            stt_client, stt_model, endpoint_info = loop.run_until_complete(
                                get_stt_client(base_url=local_url)
                            )
                            
                            if not stt_client:
                                logger.warning("Wake word STT: Local Whisper not available")
                                return ""
                            
                            logger.info(f"Wake word STT: Sending to local Whisper at {local_url}")
                            
                            # Use internal STT implementation to avoid failover
                            stt_config = {
                                'client': stt_client,
                                'model': stt_model,
                                'base_url': local_url,
                                'provider': 'whisper-local'
                            }
                            
                            text = loop.run_until_complete(
                                _speech_to_text_internal(
                                    audio_chunk,
                                    stt_config,
                                    {'_temp_stt': stt_client}
                                )
                            )
                            
                            if text:
                                logger.info(f"Wake word STT result: '{text}'")
                            else:
                                logger.debug("Wake word STT: No speech detected (silence is OK)")
                            
                            return text or ""
                        else:
                            # Use normal STT with failover
                            logger.info("Wake word STT: Using normal mode with failover")
                            text = loop.run_until_complete(
                                speech_to_text(audio_chunk)
                            )
                            return text or ""
                    finally:
                        loop.close()
                except Exception as e:
                    logger.error(f"Wake word STT callback error: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    return ""
            
            # Create wake word callback with threading coordination
            wake_detected = threading.Event()
            detected_data = {"text": "", "wake_word": ""}
            
            def wake_callback(wake_word: str, full_text: str):
                """Callback when wake word is detected."""
                detected_data["wake_word"] = wake_word
                detected_data["text"] = full_text
                wake_detected.set()
            
            # Start wake word detection service
            service = WakeWordDetectionService(
                wake_config,
                stt_callback_sync,
                wake_callback
            )
            
            service.start()
            
            try:
                # Wait for wake word detection
                logger.info("Waiting for wake word...")
                wake_detected.wait()  # This blocks until wake word detected
                
                # Extract the utterance after the wake word
                wake_word_text = detected_data["wake_word"]
                full_text = detected_data["text"]
                
                # Find what comes after the wake word
                if wake_word_text and full_text:
                    # Extract just the part after the wake word
                    wake_pos = full_text.lower().find(wake_word_text.split()[-1].lower())
                    if wake_pos >= 0:
                        # Get everything after the wake word
                        after_wake = full_text[wake_pos + len(wake_word_text.split()[-1]):].strip()
                        if after_wake:
                            message = after_wake
                            logger.info(f"Processing wake word request: '{message}'")
                        else:
                            # Just the wake word, no command
                            message = "Yes?"
                            wait_for_response = True
                    else:
                        message = full_text
                
                # Continue with normal conversation flow
                # The rest of the function will handle speaking the message
                
            finally:
                service.stop()
                
        except Exception as e:
            logger.error(f"Wake word detection error: {e}")
            logger.error(traceback.format_exc())
            return f"❌ Wake word detection error: {str(e)}"
    
    # Validate duration parameters
    if wait_for_response:
        if min_listen_duration < 0:
            return "❌ Error: min_listen_duration cannot be negative"
        if listen_duration <= 0:
            return "❌ Error: listen_duration must be positive"
        if min_listen_duration > listen_duration:
            logger.warning(f"min_listen_duration ({min_listen_duration}s) is greater than listen_duration ({listen_duration}s), using listen_duration as minimum")
            min_listen_duration = listen_duration
    
    # Check if FFmpeg is available
    ffmpeg_available = getattr(voice_mode.config, 'FFMPEG_AVAILABLE', True)  # Default to True if not set
    if not ffmpeg_available:
        from ..utils.ffmpeg_check import get_install_instructions
        error_msg = (
            "FFmpeg is required for voice features but is not installed.\n\n"
            f"{get_install_instructions()}\n\n"
            "Voice features cannot work without FFmpeg."
        )
        logger.error(error_msg)
        return f"❌ Error: {error_msg}"
    
    # Run startup initialization if needed
    await startup_initialization()
    
    # Get event logger and start session
    event_logger = get_event_logger()
    session_id = None
    
    # Check time since last session for AI thinking time
    global last_session_end_time
    current_time = time.time()
    
    if last_session_end_time and wait_for_response:
        time_since_last = current_time - last_session_end_time
        logger.info(f"Time since last session: {time_since_last:.1f}s (AI thinking time)")
    
    # For conversations with responses, create a session
    if event_logger and wait_for_response:
        session_id = event_logger.start_session()
        # Log the time since last session as an event
        if last_session_end_time:
            event_logger.log_event("TIME_SINCE_LAST_SESSION", {
                "seconds": time_since_last
            })
    
    # Log tool request start (after session is created)
    if event_logger:
        # If we have a session, the event will be associated with it
        log_tool_request_start("converse", {
            "wait_for_response": wait_for_response,
            "listen_duration": listen_duration if wait_for_response else None
        })
    
    # Track execution time and resources
    start_time = time.time()
    if DEBUG:
        import resource
        start_memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        logger.debug(f"Starting converse - Memory: {start_memory} KB")
    
    result = None
    success = False
    
    try:
        # If not waiting for response, just speak and return
        if not wait_for_response:
            try:
                async with audio_operation_lock:
                    success, tts_metrics, tts_config = await text_to_speech_with_failover(
                        message=message,
                        voice=voice,
                        model=tts_model,
                        instructions=tts_instructions,
                        audio_format=audio_format,
                        initial_provider=tts_provider
                    )
                    
                # Include timing info if available
                timing_info = ""
                timing_str = ""
                if success and tts_metrics:
                    timing_info = f" (gen: {tts_metrics.get('generation', 0):.1f}s, play: {tts_metrics.get('playback', 0):.1f}s)"
                    # Create timing string for statistics
                    timing_parts = []
                    if 'ttfa' in tts_metrics:
                        timing_parts.append(f"ttfa {tts_metrics['ttfa']:.1f}s")
                    if 'generation' in tts_metrics:
                        timing_parts.append(f"tts_gen {tts_metrics['generation']:.1f}s")
                    if 'playback' in tts_metrics:
                        timing_parts.append(f"tts_play {tts_metrics['playback']:.1f}s")
                    timing_str = ", ".join(timing_parts)
                
                result = f"✓ Message spoken successfully{timing_info}" if success else "✗ Failed to speak message"
                
                # Track statistics for speak-only interaction
                track_voice_interaction(
                    message=message,
                    response="[speak-only]",
                    timing_str=timing_str if success else None,
                    transport="speak-only",
                    voice_provider=tts_provider,
                    voice_name=voice,
                    model=tts_model,
                    success=success,
                    error_message=None if success else "TTS failed"
                )
                
                # Log TTS to JSONL for speak-only mode
                if success:
                    try:
                        conversation_logger = get_conversation_logger()
                        conversation_logger.log_tts(
                            text=message,
                            audio_file=os.path.basename(tts_metrics.get('audio_path')) if tts_metrics.get('audio_path') else None,
                            model=tts_model,
                            voice=voice,
                            provider=tts_provider if tts_provider else 'openai',
                            timing=timing_str,
                            audio_format=audio_format
                        )
                    except Exception as e:
                        logger.error(f"Failed to log TTS to JSONL: {e}")
                
                logger.info(f"Speak-only result: {result}")
                # success is already set correctly from TTS result
                return result
            except Exception as e:
                logger.error(f"Speak error: {e}")
                error_msg = f"Error: {str(e)}"
                
                # Track failed speak-only interaction
                track_voice_interaction(
                    message=message,
                    response="[error]",
                    timing_str=None,
                    transport="speak-only",
                    voice_provider=tts_provider,
                    voice_name=voice,
                    model=tts_model,
                    success=False,
                    error_message=str(e)
                )
                
                logger.error(f"Returning error: {error_msg}")
                result = error_msg
                return result
        
        # Otherwise, speak and then listen for response
        # Determine transport method
        if transport == "auto":
            if await check_livekit_available():
                transport = "livekit"
                logger.info("Auto-selected LiveKit transport")
            else:
                transport = "local"
                logger.info("Auto-selected local transport")
        
        if transport == "livekit":
            # For LiveKit, use the existing function but with the message parameter
            livekit_result = await livekit_converse(message, room_name, timeout)
            
            # Track LiveKit interaction (simplified since we don't have detailed timing)
            success = not livekit_result.startswith("Error:") and not livekit_result.startswith("No ")
            track_voice_interaction(
                message=message,
                response=livekit_result,
                timing_str=None,  # LiveKit doesn't provide detailed timing
                transport="livekit",
                voice_provider="livekit",  # LiveKit manages its own providers
                voice_name=voice,
                model=tts_model,
                success=success,
                error_message=livekit_result if not success else None
            )
            
            result = livekit_result
            success = not livekit_result.startswith("Error:") and not livekit_result.startswith("No ")
            return result
        
        elif transport == "local":
            # Local microphone approach with timing
            timings = {}
            try:
                async with audio_operation_lock:
                    # Speak the message
                    tts_start = time.perf_counter()
                    tts_success, tts_metrics, tts_config = await text_to_speech_with_failover(
                        message=message,
                        voice=voice,
                        model=tts_model,
                        instructions=tts_instructions,
                        audio_format=audio_format,
                        initial_provider=tts_provider
                    )
                    
                    # Add TTS sub-metrics
                    if tts_metrics:
                        timings['ttfa'] = tts_metrics.get('ttfa', 0)
                        timings['tts_gen'] = tts_metrics.get('generation', 0)
                        timings['tts_play'] = tts_metrics.get('playback', 0)
                    timings['tts_total'] = time.perf_counter() - tts_start
                    
                    if not tts_success:
                        result = "Error: Could not speak message"
                        return result
                    
                    # Brief pause before listening
                    await asyncio.sleep(0.5)
                    
                    # Play "listening" feedback sound
                    await play_audio_feedback("listening", openai_clients, audio_feedback, audio_feedback_style or "whisper")
                    
                    # Record response
                    logger.info(f"🎤 Listening for {listen_duration} seconds...")
                    
                    # Log recording start
                    if event_logger:
                        event_logger.log_event(event_logger.RECORDING_START)
                    
                    record_start = time.perf_counter()
                    logger.debug(f"About to call record_audio_with_silence_detection with duration={listen_duration}, disable_silence_detection={disable_silence_detection}, min_duration={min_listen_duration}")
                    audio_data = await asyncio.get_event_loop().run_in_executor(
                        None, record_audio_with_silence_detection, listen_duration, disable_silence_detection, min_listen_duration
                    )
                    timings['record'] = time.perf_counter() - record_start
                    
                    # Log recording end
                    if event_logger:
                        event_logger.log_event(event_logger.RECORDING_END, {
                            "duration": timings['record'],
                            "samples": len(audio_data)
                        })
                    
                    # Play "finished" feedback sound
                    await play_audio_feedback("finished", openai_clients, audio_feedback, audio_feedback_style or "whisper")
                    
                    # Mark the end of recording - this is when user expects response to start
                    user_done_time = time.perf_counter()
                    logger.info(f"Recording finished at {user_done_time - tts_start:.1f}s from start")
                    
                    if len(audio_data) == 0:
                        result = "Error: Could not record audio"
                        return result
                    
                    # Convert to text
                    # Log STT start
                    if event_logger:
                        event_logger.log_event(event_logger.STT_START)
                    
                    stt_start = time.perf_counter()
                    response_text = await speech_to_text(audio_data, SAVE_AUDIO, AUDIO_DIR if SAVE_AUDIO else None)
                    timings['stt'] = time.perf_counter() - stt_start
                    
                    # Log STT complete
                    if event_logger:
                        if response_text:
                            event_logger.log_event(event_logger.STT_COMPLETE, {"text": response_text})
                        else:
                            event_logger.log_event(event_logger.STT_NO_SPEECH)
                
                # Calculate total time (use tts_total instead of sub-metrics)
                main_timings = {k: v for k, v in timings.items() if k in ['tts_total', 'record', 'stt']}
                total_time = sum(main_timings.values())
                
                # Format timing string
                timing_parts = []
                
                # Detailed breakdown
                if 'ttfa' in timings:
                    timing_parts.append(f"ttfa {timings['ttfa']:.1f}s")
                if 'tts_gen' in timings:
                    timing_parts.append(f"tts_gen {timings['tts_gen']:.1f}s")
                if 'tts_play' in timings:
                    timing_parts.append(f"tts_play {timings['tts_play']:.1f}s")
                if 'tts_total' in timings:
                    timing_parts.append(f"tts_total {timings['tts_total']:.1f}s")
                if 'record' in timings:
                    timing_parts.append(f"record {timings['record']:.1f}s")
                if 'stt' in timings:
                    timing_parts.append(f"stt {timings['stt']:.1f}s")
                
                timing_str = ", ".join(timing_parts)
                timing_str += f", total {total_time:.1f}s"
                
                # Track statistics for full conversation interaction
                actual_response = response_text or "[no speech detected]"
                track_voice_interaction(
                    message=message,
                    response=actual_response,
                    timing_str=timing_str,
                    transport=transport,
                    voice_provider=tts_provider,
                    voice_name=voice,
                    model=tts_model,
                    success=bool(response_text),  # Success if we got a response
                    error_message=None if response_text else "No speech detected"
                )
                
                # End event logging session
                if event_logger and session_id:
                    event_logger.end_session()
                
                if response_text:
                    # Save conversation transcription if enabled
                    if SAVE_TRANSCRIPTIONS:
                        conversation_text = f"Assistant: {message}\n\nUser: {response_text}"
                        metadata = {
                            "type": "conversation",
                            "transport": transport,
                            "voice": voice,
                            "model": tts_model,
                            "stt_model": "whisper-1",  # Default STT model
                            "timing": timing_str,
                            "timestamp": datetime.now().isoformat()
                        }
                        save_transcription(conversation_text, prefix="conversation", metadata=metadata)
                    
                    # Log to JSONL - TTS message first
                    try:
                        conversation_logger = get_conversation_logger()
                        # Log the TTS utterance
                        conversation_logger.log_tts(
                            text=message,
                            audio_file=os.path.basename(tts_metrics.get('audio_path')) if tts_metrics.get('audio_path') else None,
                            model=tts_model,
                            voice=voice,
                            provider=tts_provider if tts_provider else 'openai',
                            timing=timing_str,
                            audio_format=audio_format
                        )
                        
                        # Log the STT response
                        conversation_logger.log_stt(
                            text=response_text,
                            model='whisper-1',  # Default STT model
                            provider='openai',
                            audio_format='mp3'
                        )
                    except Exception as e:
                        logger.error(f"Failed to log conversation to JSONL: {e}")
                    
                    result = f"Voice response: {response_text} | Timing: {timing_str}"
                    success = True
                else:
                    result = f"No speech detected | Timing: {timing_str}"
                    success = True  # Not an error, just no speech
                return result
                    
            except Exception as e:
                logger.error(f"Local voice error: {e}")
                if DEBUG:
                    logger.error(f"Traceback: {traceback.format_exc()}")
                
                # Track failed conversation interaction
                track_voice_interaction(
                    message=message,
                    response="[error]",
                    timing_str=None,
                    transport=transport,
                    voice_provider=tts_provider,
                    voice_name=voice,
                    model=tts_model,
                    success=False,
                    error_message=str(e)
                )
                
                result = f"Error: {str(e)}"
                return result
            
        else:
            result = f"Unknown transport: {transport}"
            return result
            
    except Exception as e:
        logger.error(f"Unexpected error in converse: {e}")
        if DEBUG:
            logger.error(f"Full traceback: {traceback.format_exc()}")
        result = f"Unexpected error: {str(e)}"
        return result
        
    finally:
        # Log tool request end
        if event_logger:
            log_tool_request_end("converse", success=success)
        
        # Update last session end time for tracking AI thinking time
        if wait_for_response:
            last_session_end_time = time.time()
        
        # Log execution metrics
        elapsed = time.time() - start_time
        logger.info(f"Converse completed in {elapsed:.2f}s")
        
        if DEBUG:
            import resource
            import gc
            end_memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            memory_delta = end_memory - start_memory
            logger.debug(f"Memory delta: {memory_delta} KB (start: {start_memory}, end: {end_memory})")
            
            # Force garbage collection
            collected = gc.collect()
            logger.debug(f"Garbage collected {collected} objects")




@mcp.tool()
async def voice_registry() -> str:
    """Get the current voice provider registry showing all discovered endpoints.
    
    Returns a formatted view of all TTS and STT endpoints with their:
    - Health status
    - Available models
    - Available voices (TTS only)
    - Response times
    - Last health check time
    
    This allows the LLM to see what voice services are currently available.
    """
    # Ensure registry is initialized
    await provider_registry.initialize()
    
    # Get registry data
    registry_data = provider_registry.get_registry_for_llm()
    
    # Format the output
    lines = ["Voice Provider Registry", "=" * 50, ""]
    
    # TTS Endpoints
    lines.append("TTS Endpoints:")
    lines.append("-" * 30)
    
    for url, info in registry_data["tts"].items():
        status = "✅" if info["healthy"] else "❌"
        lines.append(f"\n{status} {url}")
        
        if info["healthy"]:
            lines.append(f"   Models: {', '.join(info['models']) if info['models'] else 'none detected'}")
            lines.append(f"   Voices: {', '.join(info['voices']) if info['voices'] else 'none detected'}")
            if info["response_time_ms"]:
                lines.append(f"   Response Time: {info['response_time_ms']:.0f}ms")
        else:
            if info.get("error"):
                lines.append(f"   Error: {info['error']}")
        
        lines.append(f"   Last Check: {info['last_check']}")
    
    # STT Endpoints
    lines.append("\n\nSTT Endpoints:")
    lines.append("-" * 30)
    
    for url, info in registry_data["stt"].items():
        status = "✅" if info["healthy"] else "❌"
        lines.append(f"\n{status} {url}")
        
        if info["healthy"]:
            lines.append(f"   Models: {', '.join(info['models']) if info['models'] else 'none detected'}")
            if info["response_time_ms"]:
                lines.append(f"   Response Time: {info['response_time_ms']:.0f}ms")
        else:
            if info.get("error"):
                lines.append(f"   Error: {info['error']}")
        
        lines.append(f"   Last Check: {info['last_check']}")
    
    return "\n".join(lines)


async def voice_chat(
    initial_message: Optional[str] = None,
    max_turns: int = 10,
    listen_duration: float = 15.0,
    voice: Optional[str] = None,
    tts_provider: Optional[Literal["openai", "kokoro"]] = None
) -> str:
    """Start an interactive voice chat session.
    
    PRIVACY NOTICE: This tool will access your microphone for the duration
    of the chat session. Say "goodbye", "exit", or "end chat" to stop.
    
    Args:
        initial_message: Optional greeting to start the conversation
        max_turns: Maximum number of conversation turns (default: 10)
        listen_duration: How long to listen each turn in seconds (default: 15.0)
        voice: Override TTS voice
        tts_provider: TTS provider to use - "openai" or "kokoro"
    
    Returns:
        Summary of the conversation
    
    Note: This is a simplified version. The full voice-chat command provides
    a more interactive experience with the LLM handling the conversation flow.
    """
    transcript = []
    
    # Start with initial message if provided
    if initial_message:
        result = await converse(
            message=initial_message,
            wait_for_response=True,
            listen_duration=listen_duration,
            voice=voice,
            tts_provider=tts_provider
        )
        transcript.append(f"Assistant: {initial_message}")
        if "Voice response:" in result:
            user_response = result.split("Voice response:")[1].split("|")[0].strip()
            transcript.append(f"User: {user_response}")
            
            # Check for exit phrases
            exit_phrases = ["goodbye", "exit", "end chat", "stop", "quit"]
            if any(phrase in user_response.lower() for phrase in exit_phrases):
                return "\n".join(transcript) + "\n\nChat ended by user."
    
    # Continue conversation for remaining turns
    turns_remaining = max_turns - (1 if initial_message else 0)
    
    return f"Voice chat started. Use the converse tool in a loop to continue the conversation.\n\nTranscript so far:\n" + "\n".join(transcript)
