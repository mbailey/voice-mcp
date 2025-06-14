"""
Voice MCP Server implementation.

This module contains the main server logic for the voice-mcp MCP server.
"""

import asyncio
import logging
import os
import sys
import traceback
import gc
import time
import atexit
import signal
from datetime import datetime
from typing import Optional, Literal
from pathlib import Path

import anyio
import sounddevice as sd
import numpy as np
from scipy.io.wavfile import write
from pydub import AudioSegment

from fastmcp import FastMCP

from .core import (
    get_openai_clients,
    text_to_speech,
    cleanup as cleanup_clients,
    save_debug_file,
    get_debug_filename
)

# Workaround for sounddevice stderr redirection issue
# This prevents sounddevice from redirecting stderr to /dev/null
# which can interfere with audio playback in MCP server context
def disable_sounddevice_stderr_redirect():
    """Comprehensively disable sounddevice's stderr redirection"""
    try:
        # Method 1: Override _ignore_stderr in various locations
        if hasattr(sd, '_sounddevice'):
            if hasattr(sd._sounddevice, '_ignore_stderr'):
                sd._sounddevice._ignore_stderr = lambda: None
        if hasattr(sd, '_ignore_stderr'):
            sd._ignore_stderr = lambda: None
        
        # Method 2: Override _check_error if it exists
        if hasattr(sd, '_check'):
            original_check = sd._check
            def safe_check(*args, **kwargs):
                # Prevent any stderr manipulation
                return original_check(*args, **kwargs)
            sd._check = safe_check
        
        # Method 3: Protect file descriptors
        import sys
        original_stderr = sys.stderr
        
        # Create a hook to prevent stderr replacement
        def protect_stderr():
            if sys.stderr != original_stderr:
                sys.stderr = original_stderr
        
        # Install protection
        import atexit
        atexit.register(protect_stderr)
        
    except Exception as e:
        # Log but continue - audio might still work
        if DEBUG:
            # Can't use logger here as it's not initialized yet
            print(f"DEBUG: Could not fully disable sounddevice stderr redirect: {e}", file=sys.stderr)

disable_sounddevice_stderr_redirect()

# Environment variables are loaded by the shell/MCP client

# Debug configuration
DEBUG = os.getenv("VOICE_MCP_DEBUG", "").lower() in ("true", "1", "yes", "on")
TRACE_DEBUG = os.getenv("VOICE_MCP_DEBUG", "").lower() == "trace"
DEBUG_DIR = Path.home() / "voice-mcp_recordings"

# Audio saving configuration
SAVE_AUDIO = os.getenv("VOICE_MCP_SAVE_AUDIO", "").lower() in ("true", "1", "yes", "on")
AUDIO_DIR = Path.home() / "voice-mcp_audio"

if DEBUG:
    DEBUG_DIR.mkdir(exist_ok=True)

if SAVE_AUDIO:
    AUDIO_DIR.mkdir(exist_ok=True)

# Configure logging
log_level = logging.DEBUG if DEBUG else logging.INFO
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("voice-mcp")

# Trace logging setup
if TRACE_DEBUG:
    trace_file = Path.home() / "voice_mcp_trace.log"
    trace_logger = logging.getLogger("voice-mcp-trace")
    trace_handler = logging.FileHandler(trace_file, mode='a')
    trace_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
    trace_logger.addHandler(trace_handler)
    trace_logger.setLevel(logging.DEBUG)
    
    def trace_calls(frame, event, arg):
        if event == 'call':
            code = frame.f_code
            if 'voice-mcp' in code.co_filename or 'voice_mcp' in code.co_filename:
                trace_logger.debug(f"Called {code.co_filename}:{frame.f_lineno} {code.co_name}")
        elif event == 'exception':
            trace_logger.debug(f"Exception: {arg}")
        return trace_calls
    
    sys.settrace(trace_calls)
    logger.info(f"Trace debugging enabled, writing to: {trace_file}")

# Also log to file in debug mode
if DEBUG:
    debug_log_file = Path.home() / "voice_mcp_debug.log"
    file_handler = logging.FileHandler(debug_log_file, mode='a')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    logger.info(f"Debug logging to file: {debug_log_file}")

# Suppress verbose binary data in HTTP logs
if DEBUG:
    # Keep our debug logs but reduce HTTP client verbosity
    logging.getLogger("openai._base_client").setLevel(logging.INFO)
    logging.getLogger("httpcore").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.INFO)

# Create MCP server
mcp = FastMCP("Voice MCP")

# Audio configuration
SAMPLE_RATE = 44100
CHANNELS = 1

# Concurrency control for audio operations
# This prevents multiple audio operations from interfering with stdio
audio_operation_lock = asyncio.Lock()

# Service configuration
STT_BASE_URL = os.getenv("STT_BASE_URL", "https://api.openai.com/v1")
TTS_BASE_URL = os.getenv("TTS_BASE_URL", "https://api.openai.com/v1")
TTS_VOICE = os.getenv("TTS_VOICE", "nova")
TTS_MODEL = os.getenv("TTS_MODEL", "tts-1")
STT_MODEL = os.getenv("STT_MODEL", "whisper-1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Provider-specific TTS configuration
OPENAI_TTS_BASE_URL = os.getenv("OPENAI_TTS_BASE_URL", "https://api.openai.com/v1")
KOKORO_TTS_BASE_URL = os.getenv("KOKORO_TTS_BASE_URL", os.getenv("TTS_BASE_URL", "http://localhost:8880/v1"))

# LiveKit configuration
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "ws://localhost:7880")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "secret")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY is required")

logger.info("✓ MP3 support available (Python 3.11 + pydub)")

# Initialize clients with provider-specific TTS clients
openai_clients = get_openai_clients(OPENAI_API_KEY, STT_BASE_URL, TTS_BASE_URL)

# Add provider-specific TTS clients
from openai import AsyncOpenAI
import httpx

# Configure timeouts and connection pooling (same as in core.py)
http_client_config = {
    'timeout': httpx.Timeout(30.0, connect=5.0),
    'limits': httpx.Limits(max_keepalive_connections=5, max_connections=10),
}

# Create OpenAI TTS client if different from default
if OPENAI_TTS_BASE_URL != TTS_BASE_URL:
    openai_clients['tts_openai'] = AsyncOpenAI(
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_TTS_BASE_URL,
        http_client=httpx.AsyncClient(**http_client_config)
    )

# Create Kokoro TTS client if different from default
if KOKORO_TTS_BASE_URL != TTS_BASE_URL:
    openai_clients['tts_kokoro'] = AsyncOpenAI(
        api_key=OPENAI_API_KEY,
        base_url=KOKORO_TTS_BASE_URL,
        http_client=httpx.AsyncClient(**http_client_config)
    )


def get_tts_config(provider: Optional[str] = None, voice: Optional[str] = None, model: Optional[str] = None, instructions: Optional[str] = None):
    """Get TTS configuration based on provider selection"""
    # Auto-detect provider based on voice if not specified
    if provider is None and voice:
        # Kokoro voices start with af_ or am_
        if voice.startswith(('af_', 'am_')):
            provider = "kokoro"
        else:
            provider = "openai"
    
    # Default to environment configuration
    if provider is None:
        # If TTS_BASE_URL is set to something other than OpenAI, assume Kokoro
        if TTS_BASE_URL and "openai.com" not in TTS_BASE_URL:
            provider = "kokoro"
        else:
            provider = "openai"
    
    # Validate instructions usage
    if instructions and model != "gpt-4o-mini-tts":
        logger.warning(f"Instructions parameter is only supported with gpt-4o-mini-tts model, ignoring for model: {model}")
        instructions = None
    
    if provider == "kokoro":
        # Use kokoro-specific client if available, otherwise use default
        client_key = 'tts_kokoro' if 'tts_kokoro' in openai_clients else 'tts'
        return {
            'client_key': client_key,
            'base_url': KOKORO_TTS_BASE_URL,
            'model': model or 'tts-1',  # Kokoro uses OpenAI-compatible model name
            'voice': voice or 'af_sky',  # Default Kokoro voice
            'instructions': None  # Kokoro doesn't support instructions
        }
    else:  # openai
        # Use openai-specific client if available, otherwise use default
        client_key = 'tts_openai' if 'tts_openai' in openai_clients else 'tts'
        return {
            'client_key': client_key,
            'base_url': OPENAI_TTS_BASE_URL,
            'model': model or TTS_MODEL,  # Use provided model or default
            'voice': voice or TTS_VOICE,  # Default OpenAI voice
            'instructions': instructions  # Pass through instructions for OpenAI
        }


async def speech_to_text(audio_data: np.ndarray, save_audio: bool = False, audio_dir: Optional[Path] = None) -> Optional[str]:
    """Convert audio to text"""
    logger.info(f"STT: Converting speech to text, audio data shape: {audio_data.shape}")
    if DEBUG:
        logger.debug(f"STT config - Model: {STT_MODEL}, Base URL: {STT_BASE_URL}")
        logger.debug(f"Audio stats - Min: {audio_data.min()}, Max: {audio_data.max()}, Mean: {audio_data.mean():.2f}")
    
    wav_file = None
    mp3_file = None
    try:
        import tempfile
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
                        audio_path = save_debug_file(f.read(), "stt", "wav", audio_dir, True)
                        if audio_path:
                            logger.info(f"STT audio saved to: {audio_path}")
                except Exception as e:
                    logger.error(f"Failed to save audio WAV: {e}")
        
        try:
            # Convert WAV to MP3 for smaller upload
            logger.debug("Converting WAV to MP3 for upload...")
            audio = AudioSegment.from_wav(wav_file)
            logger.debug(f"Audio loaded - Duration: {len(audio)}ms, Channels: {audio.channels}, Frame rate: {audio.frame_rate}")
            
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as mp3_file_obj:
                mp3_file = mp3_file_obj.name
                audio.export(mp3_file, format="mp3", bitrate="64k")
                upload_file = mp3_file
                logger.debug(f"MP3 created for STT upload: {upload_file}")
            
            # Save debug file for upload version
            if DEBUG:
                try:
                    with open(upload_file, 'rb') as f:
                        debug_path = save_debug_file(f.read(), "stt-upload", "mp3", DEBUG_DIR, DEBUG)
                        if debug_path:
                            logger.info(f"Upload audio saved to: {debug_path}")
                except Exception as e:
                    logger.error(f"Failed to save debug MP3: {e}")
            
            # Get file size for logging
            file_size = os.path.getsize(upload_file)
            logger.debug(f"Uploading {file_size} bytes to STT API...")
            
            with open(upload_file, 'rb') as audio_file:
                # Use async context manager if available, otherwise use regular create
                transcription = await openai_clients['stt'].audio.transcriptions.create(
                    model=STT_MODEL,
                    file=audio_file,
                    response_format="text"
                )
                
                logger.debug(f"STT API response type: {type(transcription)}")
                text = transcription.strip() if isinstance(transcription, str) else transcription.text.strip()
                
                if text:
                    logger.info(f"✓ STT result: '{text}'")
                    return text
                else:
                    logger.warning("STT returned empty text")
                    return None
                        
        except Exception as e:
            logger.error(f"STT failed: {e}")
            logger.error(f"STT config when error occurred - Model: {STT_MODEL}, Base URL: {STT_BASE_URL}")
            if hasattr(e, 'response'):
                logger.error(f"HTTP status: {e.response.status_code if hasattr(e.response, 'status_code') else 'unknown'}")
                logger.error(f"Response text: {e.response.text if hasattr(e.response, 'text') else 'unknown'}")
            return None
    finally:
        # Clean up temporary files
        if wav_file and os.path.exists(wav_file):
            try:
                os.unlink(wav_file)
                logger.debug(f"Cleaned up WAV file: {wav_file}")
            except Exception as e:
                logger.error(f"Failed to clean up WAV file: {e}")
        
        if mp3_file and os.path.exists(mp3_file):
            try:
                os.unlink(mp3_file)
                logger.debug(f"Cleaned up MP3 file: {mp3_file}")
            except Exception as e:
                logger.error(f"Failed to clean up MP3 file: {e}")


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


async def livekit_ask_voice_question(question: str, room_name: str = "", timeout: float = 60.0) -> str:
    """Ask voice question using LiveKit transport"""
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
        tts_client = lk_openai.TTS(voice=TTS_VOICE, base_url=TTS_BASE_URL, model=TTS_MODEL)
        stt_client = lk_openai.STT(base_url=STT_BASE_URL, model=STT_MODEL)
        
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
            
            async def on_enter(self):
                await asyncio.sleep(0.5)
                if self.session:
                    await self.session.say(question, allow_interruptions=True)
                    self.has_spoken = True
            
            async def on_user_turn_completed(self, chat_ctx, new_message):
                if self.has_spoken and not self.response and new_message.content:
                    self.response = new_message.content[0]
        
        # Connect and run
        token = api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        token.with_identity("voice-mcp-bot").with_name("Voice MCP Bot")
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
        vad = silero.VAD.load()
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
    listen_duration: float = 10.0,
    transport: Literal["auto", "local", "livekit"] = "auto",
    room_name: str = "",
    timeout: float = 60.0,
    voice: Optional[str] = None,
    tts_provider: Optional[Literal["openai", "kokoro"]] = None,
    tts_model: Optional[str] = None,
    tts_instructions: Optional[str] = None
) -> str:
    """Have a voice conversation - speak a message and optionally listen for response
    This is the primary function for voice interactions. It combines speaking and listening
    in a natural conversational flow.
    
    PRIVACY NOTICE: When wait_for_response is True, this tool will access your microphone
    to record audio for speech-to-text conversion. Audio is processed using the configured
    STT service and is not permanently stored.
    
    Args:
        message: The message to speak
        wait_for_response: Whether to listen for a response after speaking (default: True)
        listen_duration: How long to listen for response in seconds (default: 10.0)
        transport: Transport method - "auto" (try LiveKit then local), "local" (direct mic), "livekit" (room-based)
        room_name: LiveKit room name (only for livekit transport, auto-discovered if empty)
        timeout: Maximum wait time for response in seconds (LiveKit only)
        voice: Override TTS voice (e.g., OpenAI: nova, shimmer; Kokoro: af_sky, af_sarah, am_adam, af_nicole, am_michael)
               IMPORTANT: Never use 'coral' voice. For Kokoro, always default to 'af_sky'
        tts_provider: TTS provider to use - "openai" or "kokoro" (auto-detects based on voice if not specified)
        tts_model: TTS model to use (e.g., OpenAI: tts-1, tts-1-hd, gpt-4o-mini-tts; Kokoro uses tts-1)
                   IMPORTANT: gpt-4o-mini-tts is BEST for emotional speech and should be used when expressing emotions
        tts_instructions: Tone/style instructions for gpt-4o-mini-tts model only (e.g., "Speak in a cheerful tone", "Sound angry", "Be extremely sad")
        If wait_for_response is False: Confirmation that message was spoken
        If wait_for_response is True: The voice response received (or error/timeout message)
    
    Examples:
        - Ask a question: converse("What's your name?")
        - Make a statement and wait: converse("Tell me more about that")
        - Just speak without waiting: converse("Goodbye!", wait_for_response=False)
        - Use HD model: converse("High quality speech", tts_model="tts-1-hd")
        - Express emotions: converse("I'm so excited!", tts_model="gpt-4o-mini-tts", tts_instructions="Sound extremely excited")
        - Emotional speech: converse("This is terrible", tts_model="gpt-4o-mini-tts", voice="sage", tts_instructions="Sound very sad")
    """
    logger.info(f"Converse: '{message[:50]}{'...' if len(message) > 50 else ''}' (wait_for_response: {wait_for_response})")
    
    # Track execution time and resources
    start_time = time.time()
    if DEBUG:
        import resource
        start_memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        logger.debug(f"Starting converse - Memory: {start_memory} KB")
    
    try:
        # If not waiting for response, just speak and return
        if not wait_for_response:
            try:
                async with audio_operation_lock:
                    tts_config = get_tts_config(tts_provider, voice, tts_model, tts_instructions)
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
                        client_key=tts_config['client_key'],
                        instructions=tts_config.get('instructions')
                    )
                    
                # Include timing info if available
                timing_info = ""
                if success and tts_metrics:
                    timing_info = f" (gen: {tts_metrics.get('generation', 0):.1f}s, play: {tts_metrics.get('playback', 0):.1f}s)"
                
                result = f"✓ Message spoken successfully{timing_info}" if success else "✗ Failed to speak message"
                logger.info(f"Speak-only result: {result}")
                return result
            except Exception as e:
                logger.error(f"Speak error: {e}")
                error_msg = f"Error: {str(e)}"
                logger.error(f"Returning error: {error_msg}")
                return error_msg
        
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
            return await livekit_ask_voice_question(message, room_name, timeout)
        
        elif transport == "local":
            # Local microphone approach with timing
            timings = {}
            try:
                async with audio_operation_lock:
                    # Speak the message
                    tts_start = time.perf_counter()
                    tts_config = get_tts_config(tts_provider, voice, tts_model, tts_instructions)
                    tts_success, tts_metrics = await text_to_speech(
                        text=message,
                        openai_clients=openai_clients,
                        tts_model=tts_config['model'],
                        tts_base_url=tts_config['base_url'],
                        tts_voice=tts_config['voice'],
                        debug=DEBUG,
                        debug_dir=DEBUG_DIR if DEBUG else None,
                        save_audio=SAVE_AUDIO,
                        audio_dir=AUDIO_DIR if SAVE_AUDIO else None,
                        client_key=tts_config['client_key'],
                        instructions=tts_config.get('instructions')
                    )
                    
                    # Add TTS sub-metrics
                    if tts_metrics:
                        timings['tts_gen'] = tts_metrics.get('generation', 0)
                        timings['tts_play'] = tts_metrics.get('playback', 0)
                    timings['tts_total'] = time.perf_counter() - tts_start
                    
                    if not tts_success:
                        return "Error: Could not speak message"
                    
                    # Brief pause before listening
                    await asyncio.sleep(0.5)
                    
                    # Record response
                    logger.info(f"🎤 Listening for {listen_duration} seconds...")
                    record_start = time.perf_counter()
                    audio_data = await asyncio.get_event_loop().run_in_executor(
                        None, record_audio, listen_duration
                    )
                    timings['record'] = time.perf_counter() - record_start
                    
                    if len(audio_data) == 0:
                        return "Error: Could not record audio"
                    
                    # Convert to text
                    stt_start = time.perf_counter()
                    response_text = await speech_to_text(audio_data, SAVE_AUDIO, AUDIO_DIR if SAVE_AUDIO else None)
                    timings['stt'] = time.perf_counter() - stt_start
                
                # Calculate total time (use tts_total instead of sub-metrics)
                main_timings = {k: v for k, v in timings.items() if k in ['tts_total', 'record', 'stt']}
                total_time = sum(main_timings.values())
                
                # Format timing string with sub-metrics
                timing_parts = []
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
                
                if response_text:
                    return f"Voice response: {response_text} | Timing: {timing_str}"
                else:
                    return f"No speech detected | Timing: {timing_str}"
                    
            except Exception as e:
                logger.error(f"Local voice error: {e}")
                if DEBUG:
                    logger.error(f"Traceback: {traceback.format_exc()}")
                return f"Error: {str(e)}"
            
        else:
            return f"Unknown transport: {transport}"
            
    except Exception as e:
        logger.error(f"Unexpected error in converse: {e}")
        if DEBUG:
            logger.error(f"Full traceback: {traceback.format_exc()}")
        return f"Unexpected error: {str(e)}"
        
    finally:
        # Log execution metrics
        elapsed = time.time() - start_time
        logger.info(f"Converse completed in {elapsed:.2f}s")
        
        if DEBUG:
            import resource
            end_memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            memory_delta = end_memory - start_memory
            logger.debug(f"Memory delta: {memory_delta} KB (start: {start_memory}, end: {end_memory})")
            
            # Force garbage collection
            collected = gc.collect()
            logger.debug(f"Garbage collected {collected} objects")


@mcp.tool()
async def listen_for_speech(duration: float = 5.0) -> str:
    """Listen for speech and convert to text
    
    PRIVACY NOTICE: This tool will access your microphone to record audio
    for the specified duration. Audio is processed locally and converted
    to text using the configured STT service.
    
    Args:
        duration: How long to listen in seconds
    """
    logger.info(f"Listening for {duration}s...")
    
    try:
        async with audio_operation_lock:
            logger.info(f"🎤 Recording for {duration} seconds...")
            
            audio_data = await asyncio.get_event_loop().run_in_executor(
                None, record_audio, duration
            )
            
            if len(audio_data) == 0:
                return "Error: Could not record audio"
            
            response_text = await speech_to_text(audio_data, SAVE_AUDIO, AUDIO_DIR if SAVE_AUDIO else None)
            
            if response_text:
                return f"Speech detected: {response_text}"
            else:
                return "No speech detected"
            
    except Exception as e:
        logger.error(f"Listen error: {e}")
        return f"Error: {str(e)}"


@mcp.tool()
async def check_room_status() -> str:
    """Check LiveKit room status and participants"""
    try:
        from livekit import api
        
        api_url = LIVEKIT_URL.replace("ws://", "http://").replace("wss://", "https://")
        lk_api = api.LiveKitAPI(api_url, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        
        rooms = await lk_api.room.list_rooms(api.ListRoomsRequest())
        if not rooms.rooms:
            return "No active LiveKit rooms"
        
        status = []
        for room in rooms.rooms:
            participants = await lk_api.room.list_participants(
                api.ListParticipantsRequest(room=room.name)
            )
            
            status.append(f"• {room.name} ({room.num_participants} participants)")
            for p in participants.participants:
                status.append(f"  - {p.identity}")
        
        return "\n".join(status)
        
    except Exception as e:
        logger.error(f"Room status error: {e}")
        return f"Error checking room status: {str(e)}"


@mcp.tool()
async def check_audio_devices() -> str:
    """List available audio input and output devices"""
    try:
        devices = sd.query_devices()
        input_devices = []
        output_devices = []
        
        for i, device in enumerate(devices):
            if device['max_input_channels'] > 0:
                input_devices.append(f"  {i}: {device['name']} (inputs: {device['max_input_channels']})")
            if device['max_output_channels'] > 0:
                output_devices.append(f"  {i}: {device['name']} (outputs: {device['max_output_channels']})")
        
        result = []
        result.append("🎤 Input Devices:")
        result.extend(input_devices if input_devices else ["  None found"])
        result.append("\n🔊 Output Devices:")
        result.extend(output_devices if output_devices else ["  None found"])
        
        default_input = sd.default.device[0] if sd.default.device[0] is not None else "None"
        default_output = sd.default.device[1] if sd.default.device[1] is not None else "None"
        
        result.append(f"\n📌 Default Input: {default_input}")
        result.append(f"📌 Default Output: {default_output}")
        
        return "\n".join(result)
        
    except Exception as e:
        return f"Error listing audio devices: {str(e)}"


async def cleanup():
    """Cleanup function to close HTTP clients and resources"""
    await cleanup_clients(openai_clients)


def main():
    """Main entry point for the server."""
    try:
        from voice_mcp import __version__
        version_info = f" v{__version__}"
    except ImportError:
        version_info = ""
    
    logger.info(f"Voice MCP Server{version_info} - Unified Transport")
    logger.info(f"Debug mode: {'ENABLED' if DEBUG else 'DISABLED'}")
    if DEBUG:
        logger.info(f"Debug recordings will be saved to: {DEBUG_DIR}")
    logger.info(f"STT: {STT_BASE_URL} (model: {STT_MODEL})")
    logger.info(f"TTS: {TTS_BASE_URL} (model: {TTS_MODEL}, voice: {TTS_VOICE})")
    logger.info(f"LiveKit: {LIVEKIT_URL}")
    logger.info(f"Sample Rate: {SAMPLE_RATE}Hz")
    
    # Register cleanup handler
    def sync_cleanup():
        try:
            # Don't try to cleanup if we're already shutting down
            if hasattr(asyncio, '_get_running_loop'):
                loop = asyncio._get_running_loop()
                if loop is not None:
                    return  # Already in an event loop context
            
            # Only run cleanup if we can create a new event loop
            try:
                asyncio.run(cleanup())
            except RuntimeError:
                pass  # Event loop already closed
        except Exception as e:
            logger.debug(f"Cleanup skipped: {e}")
    
    atexit.register(sync_cleanup)
    # Don't immediately exit on signals - let FastMCP handle shutdown
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, initiating graceful shutdown...")
        # FastMCP will handle the shutdown process
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        mcp.run()
    except (BrokenPipeError, anyio.BrokenResourceError) as e:
        logger.error(f"Connection lost to MCP client: {type(e).__name__}: {e}")
        # These errors indicate the client disconnected, which is expected behavior
        sys.exit(0)  # Exit cleanly since this is not an error condition
    except Exception as e:
        logger.error(f"Unexpected error in MCP server: {e}")
        if DEBUG:
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
        sys.exit(1)


if __name__ == "__main__":
    main()
