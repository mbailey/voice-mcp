# ASR Hallucination Prevention

## Overview
Automatic Speech Recognition (ASR) systems can generate phantom text when processing silence or background noise, creating "hallucinations" of speech that wasn't actually spoken.

## Problem Description
When Voice Mode is listening during periods of silence, the STT service may:
- Generate random words or phrases from background noise
- Create repetitive patterns (e.g., "the the the...")
- Produce nonsensical transcriptions
- Waste tokens and confuse the LLM with fake input

## Current Impact
- Occurs during long listen durations with silence
- More common with certain STT providers
- Can trigger unwanted responses
- Makes logs difficult to parse
- Wastes API credits on phantom speech

## Proposed Solutions

### 1. Voice Activity Detection (VAD)
- Implement local VAD before sending audio to STT
- Only process audio segments with detected speech
- Libraries: WebRTC VAD, Silero VAD, py-webrtcvad

### 2. Confidence Thresholds
- Use STT confidence scores when available
- Discard transcriptions below threshold
- Adjust threshold based on environment

### 3. Pattern Detection
- Identify common hallucination patterns
- Filter repetitive sequences
- Detect nonsensical word combinations

### 4. Silence Detection Enhancement
- Improve existing silence detection
- Adjust energy thresholds dynamically
- Consider frequency analysis beyond volume

### 5. Provider-Specific Tuning
- OpenAI Whisper: Adjust temperature parameter
- Local Whisper: Use VAD preprocessing
- Configure provider-specific parameters

## Implementation Approach

### Phase 1: Analysis
- Log and analyze hallucination patterns
- Identify provider-specific behaviors
- Measure frequency and impact

### Phase 2: VAD Integration
```python
def should_process_audio(audio_segment):
    # Use WebRTC VAD
    if not vad.is_speech(audio_segment):
        return False
    
    # Energy threshold check
    if audio_energy < threshold:
        return False
        
    return True
```

### Phase 3: Post-Processing Filter
```python
def filter_hallucinations(transcription):
    # Check for repetitive patterns
    if has_repetitive_pattern(transcription):
        return None
        
    # Check confidence if available
    if transcription.confidence < 0.5:
        return None
        
    # Check for common hallucination phrases
    if matches_hallucination_pattern(transcription):
        return None
        
    return transcription
```

## Testing Scenarios
1. Complete silence
2. White noise / fan noise
3. Distant conversations
4. Music playing
5. Outdoor ambient sounds
6. Various microphone types

## Success Metrics
- Hallucination rate < 1% of silent periods
- No false negatives (real speech filtered)
- Reduced STT API costs
- Improved user experience

## Related Work
- Whisper.cpp has VAD options
- OpenAI's Whisper has hallucination issues documented
- Various research on ASR robustness

## Configuration Ideas
```yaml
asr_hallucination_prevention:
  vad_enabled: true
  vad_aggressiveness: 2  # 0-3, higher = more aggressive
  confidence_threshold: 0.6
  repetition_threshold: 3
  hallucination_patterns:
    - "thank you for watching"
    - "please subscribe"
    - "the the the"
  energy_threshold_multiplier: 1.5
```

## Next Steps
1. Implement logging to capture hallucination examples
2. Test VAD libraries for effectiveness
3. Create benchmark with various silence types
4. Build filtering pipeline
5. Test with standby mode feature

## Notes
- Critical for standby mode where long listening periods are expected
- May also improve regular conversation mode
- Consider different strategies for different use cases