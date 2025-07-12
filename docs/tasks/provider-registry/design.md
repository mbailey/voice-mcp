# Voice Provider Registry Design

Based on OpenRouter's model and our requirements, here's a proposed design for the voice-mode provider registry system.

## Provider Properties

### Core Properties
```python
{
    "id": "kokoro",
    "name": "Kokoro TTS",
    "type": "tts",  # tts, stt, or both
    "status": "available",  # available, unavailable, starting, error
    
    # Endpoints
    "base_url": "http://127.0.0.1:8880/v1",
    "health_endpoint": "/health",
    "requires_auth": false,
    
    # Cost (per minute of audio)
    "cost": {
        "amount": 0.0,  # Free for local
        "unit": "per_minute",
        "currency": "USD"
    },
    
    # Performance
    "latency": {
        "first_byte_ms": 50,  # Time to first audio byte
        "processing_factor": 0.3  # Realtime factor (0.3 = 3x faster than realtime)
    },
    
    # Privacy & Security
    "privacy": {
        "level": "local",  # local, cloud_private, cloud_public
        "data_retention": "none",
        "gdpr_compliant": true
    },
    
    # Requirements
    "requirements": {
        "api_key": false,
        "local_models": true,
        "download_size_mb": 750,
        "min_memory_mb": 2048,
        "gpu_recommended": false
    },
    
    # Features (TTS-specific)
    "features": {
        "voices": ["af_sky", "af_bella", "am_adam", "am_michael"],
        "languages": ["en"],
        "max_chars": 5000,
        "emotions": false,
        "voice_cloning": false,
        "ssml_support": false,
        "audio_formats": ["mp3", "wav", "opus"]
    },
    
    # Quality metrics
    "quality": {
        "naturalness": 4.2,  # 1-5 scale
        "clarity": 4.5,
        "user_rating": 4.3
    },
    
    # Operational
    "auto_start": true,
    "startup_time_s": 5,
    "managed_by": "mcp"  # mcp, external, cloud
}
```

### STT-Specific Properties
```python
{
    "features": {
        "languages": ["multilingual"],
        "max_duration_s": 3600,
        "streaming": true,
        "punctuation": true,
        "speaker_diarization": false,
        "word_timestamps": true,
        "formats": ["wav", "mp3", "m4a", "webm"]
    },
    
    "accuracy": {
        "wer": 0.05,  # Word Error Rate
        "language_detection": 0.95
    }
}
```

## Model-Aware Provider Structure

### Enhanced Provider with Models
```python
{
    "id": "whisper-local",
    "name": "Whisper.cpp",
    "type": "stt",
    "base_url": "http://127.0.0.1:2022/v1",
    
    # Models array with specific properties
    "models": {
        "default": "base",
        "available": [
            {
                "id": "tiny",
                "size_mb": 39,
                "speed_factor": 10.0,  # 10x realtime
                "accuracy": 0.85,  # WER
                "languages": 99
            },
            {
                "id": "base", 
                "size_mb": 74,
                "speed_factor": 7.0,
                "accuracy": 0.90,
                "languages": 99
            },
            {
                "id": "small",
                "size_mb": 244,
                "speed_factor": 4.0,
                "accuracy": 0.93,
                "languages": 99
            },
            {
                "id": "medium",
                "size_mb": 769,
                "speed_factor": 2.0,
                "accuracy": 0.95,
                "languages": 99
            },
            {
                "id": "large",
                "size_mb": 1550,
                "speed_factor": 1.0,
                "accuracy": 0.97,
                "languages": 99
            }
        ]
    }
}
```

### Provider-Model Combinations
The same model can perform differently across providers:
```python
# Whisper via different providers
"whisper-providers": {
    "whisper-local": {
        "model": "large",
        "latency_ms": 100,
        "throughput": 1.0,
        "cost": 0.0
    },
    "openai-whisper": {
        "model": "whisper-1",  # Equivalent to large-v2
        "latency_ms": 500,
        "throughput": 2.0,  # Better hardware
        "cost": 0.006
    },
    "groq-whisper": {
        "model": "whisper-large-v3",
        "latency_ms": 50,  # LPU acceleration
        "throughput": 10.0,
        "cost": 0.002
    }
}
```

## Provider Registry Structure

```python
PROVIDER_REGISTRY = {
    # TTS Providers
    "openai": {
        "id": "openai",
        "name": "OpenAI TTS",
        "type": "tts",
        "base_url": "https://api.openai.com/v1",
        "cost": {"amount": 0.015, "unit": "per_1k_chars"},
        "privacy": {"level": "cloud_public"},
        "features": {
            "voices": ["alloy", "nova", "echo", "fable", "onyx", "shimmer"],
            "emotions": True,  # via gpt-4o-mini-tts
            "models": ["tts-1", "tts-1-hd", "gpt-4o-mini-tts"]
        }
    },
    
    "kokoro": {
        # ... as defined above
    },
    
    # STT Providers
    "whisper-local": {
        "id": "whisper-local",
        "name": "Whisper.cpp",
        "type": "stt",
        "base_url": "http://127.0.0.1:2022/v1",
        "cost": {"amount": 0.0},
        "privacy": {"level": "local"},
        "requirements": {
            "download_size_mb": 1500,  # For large model
            "models": ["tiny", "base", "small", "medium", "large"]
        }
    },
    
    "openai-whisper": {
        "id": "openai-whisper",
        "name": "OpenAI Whisper",
        "type": "stt",
        "base_url": "https://api.openai.com/v1",
        "cost": {"amount": 0.006, "unit": "per_minute"},
        "privacy": {"level": "cloud_public"}
    }
}
```

## Configuration System

### Environment Variables (Backward Compatible)
```bash
# Legacy support
TTS_BASE_URL=...
STT_BASE_URL=...

# New unified configuration
VOICE_PROVIDERS="kokoro,openai"  # Priority order
VOICE_TTS_PROVIDERS="kokoro,openai"  # TTS-specific order
VOICE_STT_PROVIDERS="whisper-local,openai-whisper"  # STT-specific

# Provider preferences
VOICE_PREFER_LOCAL=true  # Prioritize local providers
VOICE_MAX_COST=0.01  # Max cost per minute
VOICE_MIN_PRIVACY="cloud_private"  # Minimum privacy level

# Auto-start
VOICE_AUTO_START_LOCAL=true  # Auto-start local services
```

### Selection Logic
```python
def select_provider(
    task_type: str,  # "tts" or "stt"
    requirements: dict = None
) -> Provider:
    """
    Select best available provider based on:
    1. User-specified provider list
    2. Availability
    3. Requirements matching (e.g., needs emotions)
    4. User preferences (cost, privacy, etc.)
    5. Fallback chain
    """
    
    # Example requirements:
    # {"emotions": True} -> Would select OpenAI gpt-4o-mini-tts
    # {"privacy": "local"} -> Would select Kokoro or Whisper
    # {"max_cost": 0} -> Would select local providers only
```

## Status Display Enhancement

The unified status tool would show:
```
🎙️ VOICE SERVICES STATUS
========================================

🔊 Text-to-Speech Providers
----------------------------------------
1. Kokoro TTS (Primary)
   Status: ✅ Running (local)
   Cost: FREE
   Latency: 50ms
   Privacy: 🔒 Local
   Features: 4 voices, English

2. OpenAI TTS (Fallback)
   Status: ✅ Available
   Cost: $0.015/1k chars
   Latency: 200ms
   Privacy: ☁️ Cloud
   Features: 6 voices, emotions, 3 models

🗣️ Speech-to-Text Providers
----------------------------------------
1. Whisper.cpp (Primary)
   Status: ✅ Running (local)
   Cost: FREE
   Accuracy: 95% WER
   Privacy: 🔒 Local
   
2. OpenAI Whisper (Fallback)
   Status: ✅ Available
   Cost: $0.006/minute
   Privacy: ☁️ Cloud

💡 ACTIVE CONFIGURATION
----------------------------------------
Provider Selection: Local preferred
Max Cost: Unlimited
Auto-start: Enabled
Current TTS: Kokoro (local)
Current STT: Whisper.cpp (local)
```

## Implementation Plan

1. Create provider registry module with default providers
2. Add provider selection logic with requirements matching
3. Update configuration to support new env vars while maintaining backward compatibility
4. Enhance status tool to show provider details
5. Add provider switching commands
6. Document new configuration system