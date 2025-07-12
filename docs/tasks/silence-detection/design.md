# Silence Detection Design

## Overview

This document outlines the design for implementing silence detection in voice_mode to automatically stop recording when the user stops speaking, eliminating the need to wait for the full duration timeout.

## Problem Statement

Currently, when a user says a short response like "yes" with a 20-second duration, they must wait 17+ seconds of silence before the system processes their response. This creates a poor user experience.

## Design Goals

1. **Automatic End-of-Turn Detection**: Stop recording when user stops speaking
2. **Minimal Latency**: Detect silence quickly without cutting off speech
3. **Robustness**: Handle various speech patterns (pauses, thinking, etc.)
4. **Backwards Compatibility**: Maintain existing duration parameter as maximum
5. **Performance**: Low CPU usage for real-time processing

## Implementation Options

### Option 1: WebRTC VAD (Recommended for MVP)

**Pros:**
- Lightweight and fast
- Battle-tested in real-world applications
- Easy to integrate with existing sounddevice recording
- Low latency (10-30ms frames)

**Cons:**
- Only detects voice presence, not semantic completion
- May trigger on background noise
- Can't distinguish between thinking pauses and end of turn

**Implementation:**
```python
import webrtcvad
vad = webrtcvad.Vad(2)  # Aggressiveness 0-3
```

### Option 2: Energy-Based Detection

**Pros:**
- Simple to implement
- No additional dependencies
- Already have RMS calculation in codebase

**Cons:**
- Prone to false positives/negatives
- Requires tuning for different environments
- Less sophisticated than VAD

### Option 3: LiveKit Turn Detector Plugin (Future Enhancement)

**Pros:**
- Context-aware using transformer model
- 85% true positive rate (avoids interruptions)
- 97% true negative rate (accurate end detection)
- Handles semantic pauses ("let me think...")

**Cons:**
- Requires STT integration
- Additional 200MB model download
- More complex integration

## Proposed MVP Implementation

### Phase 1: WebRTC VAD Integration

1. **Add webrtcvad dependency**
   ```toml
   dependencies = [
       ...
       "webrtcvad>=2.0.10",
   ]
   ```

2. **Modify record_audio() function**
   - Record in chunks instead of one long recording
   - Process each chunk through VAD
   - Track silence duration
   - Stop when silence threshold exceeded

3. **Configuration parameters**
   ```python
   VAD_AGGRESSIVENESS = 2  # 0-3, higher = more aggressive
   SILENCE_THRESHOLD_MS = 800  # Stop after 800ms of silence
   MIN_RECORDING_DURATION = 0.5  # Minimum recording time
   CHUNK_DURATION_MS = 30  # VAD frame size
   ```

### Phase 2: Enhanced Detection (Future)

1. **Hybrid approach**: Combine VAD + energy detection
2. **Adaptive thresholds**: Adjust based on ambient noise
3. **Integration with LiveKit turn detector** for semantic understanding

## Technical Implementation Details

### Recording Loop Structure

```python
def record_audio_with_silence_detection(max_duration: float) -> np.ndarray:
    vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)
    
    chunks = []
    silence_duration = 0
    recording_duration = 0
    
    # Calculate chunk size (must be 10, 20, or 30ms)
    chunk_samples = int(SAMPLE_RATE * CHUNK_DURATION_MS / 1000)
    
    while recording_duration < max_duration:
        # Record chunk
        chunk = sd.rec(chunk_samples, samplerate=SAMPLE_RATE, 
                       channels=1, dtype=np.int16)
        sd.wait()
        
        # Check if chunk contains speech
        is_speech = vad.is_speech(chunk.tobytes(), SAMPLE_RATE)
        
        if is_speech:
            silence_duration = 0
        else:
            silence_duration += CHUNK_DURATION_MS
            
        chunks.append(chunk)
        recording_duration += CHUNK_DURATION_MS / 1000
        
        # Stop conditions
        if (silence_duration >= SILENCE_THRESHOLD_MS and 
            recording_duration >= MIN_RECORDING_DURATION):
            break
    
    return np.concatenate(chunks).flatten()
```

### Integration Points

1. **conversation.py**: Replace `record_audio()` with `record_audio_with_silence_detection()`
2. **Configuration**: Add VAD settings to config.py
3. **Audio feedback**: Play end chime immediately when silence detected
4. **Logging**: Add debug logs for VAD decisions

## Testing Strategy

1. **Unit Tests**
   - Test VAD with pre-recorded samples
   - Verify silence detection thresholds
   - Test edge cases (immediate silence, no silence, intermittent)

2. **Integration Tests**
   - Test with actual microphone input
   - Verify compatibility with different audio devices
   - Test various speech patterns

3. **Performance Tests**
   - Measure CPU usage during recording
   - Verify real-time processing capability
   - Test with different chunk sizes

## Migration Path

1. **Feature flag**: Add `ENABLE_SILENCE_DETECTION` environment variable
2. **Gradual rollout**: Default to disabled, let users opt-in
3. **Telemetry**: Log detection accuracy metrics
4. **Feedback loop**: Adjust thresholds based on usage

## Success Metrics

1. **Latency reduction**: Average time saved per interaction
2. **Accuracy**: False positive/negative rates
3. **User satisfaction**: Fewer complaints about waiting
4. **Performance**: CPU usage stays under 5%

## Future Enhancements

1. **Adaptive silence threshold**: Learn from user patterns
2. **Multi-modal detection**: Combine with visual cues (if available)
3. **Language-specific models**: Different thresholds for different languages
4. **Noise cancellation**: Pre-process audio before VAD
5. **LiveKit integration**: Use their transformer model for semantic detection

## Risks and Mitigations

1. **Risk**: Cutting off user mid-sentence
   - **Mitigation**: Conservative thresholds, minimum recording time

2. **Risk**: Background noise triggering VAD
   - **Mitigation**: Adjustable aggressiveness, energy-based validation

3. **Risk**: Performance impact on low-end devices
   - **Mitigation**: Efficient chunk processing, optional feature

## References

- [WebRTC VAD Documentation](https://github.com/wiseman/py-webrtcvad)
- [LiveKit Turn Detection Blog](https://blog.livekit.io/using-a-transformer-to-improve-end-of-turn-detection/)
- [Silero VAD](https://github.com/snakers4/silero-vad)