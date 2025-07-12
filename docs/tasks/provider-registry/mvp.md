# Provider Registry MVP Implementation Plan

## Phase 1: Minimal Viable Implementation

### 1. Create Basic Provider Registry (Day 1)
```python
# voice_mode/providers.py
PROVIDERS = {
    "kokoro": {
        "id": "kokoro",
        "name": "Kokoro TTS", 
        "type": "tts",
        "base_url": "http://127.0.0.1:8880/v1",
        "local": True,
        "auto_start": True,
        "features": ["local", "free", "fast"]
    },
    "openai": {
        "id": "openai",
        "name": "OpenAI TTS",
        "type": "tts", 
        "base_url": "https://api.openai.com/v1",
        "local": False,
        "features": ["cloud", "emotions", "multi-model"]
    },
    "whisper": {
        "id": "whisper",
        "name": "Whisper.cpp",
        "type": "stt",
        "base_url": "http://127.0.0.1:2022/v1", 
        "local": True,
        "features": ["local", "free", "accurate"]
    }
}
```

### 2. Simple Provider Selection (Day 1)
```python
def get_tts_provider(prefer_local=True):
    """Get best available TTS provider"""
    if prefer_local and is_available("kokoro"):
        return PROVIDERS["kokoro"]
    elif is_available("openai"):
        return PROVIDERS["openai"]
    return None

def is_available(provider_id):
    """Check if provider is reachable"""
    # Simple health check
```

### 3. Update Existing Functions (Day 2)
- Modify `get_tts_config()` to use provider registry
- Update `converse()` to use provider selection
- Keep backward compatibility with existing env vars

### 4. Enhanced Status Display (Day 2)
Update `voice_status()` to show:
- Available providers
- Which is currently active
- Simple fallback chain

### 5. Auto-start Integration (Day 3)
- Use existing `startup_initialization()`
- Check provider registry for auto_start flag
- Start local services as needed

## What We're NOT Doing Yet
- Complex cost calculations
- Model-specific properties
- Advanced provider selection logic
- Multiple providers of same model
- Quality metrics

## Success Criteria
1. Kokoro auto-starts if configured
2. Falls back to OpenAI if Kokoro fails
3. Status shows clear provider info
4. No breaking changes to existing setup

## Next Steps After MVP
- Add model selection
- Implement cost tracking
- Add more providers
- Build preference system