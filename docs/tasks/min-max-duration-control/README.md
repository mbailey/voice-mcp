# Min/Max Duration Control for Voice Response

## Overview

Add LLM control over minimum and maximum listening duration to prevent premature cutoffs and handle various conversational patterns more effectively.

## Background Research

This is an established pattern in speech recognition systems:

### Industry Standards
- **Minimum Speech Duration**: Typically 200-300ms to filter out brief noises
- **Silence Duration**: Typically 500-700ms to detect end of speech
- **WebRTC VAD**: Works with 10, 20, or 30ms chunks
- **AssemblyAI**: Uses `min_end_of_turn_silence_when_confident` (default 160ms, recommended 560ms for conversations)
- **OpenAI Realtime API**: Uses `prefix_padding_ms` and `silence_duration_ms`

### Use Cases
1. **Minimum Duration**:
   - Prevent cutting off slow starters
   - Handle people who pause before speaking
   - Accommodate thinking time before responses
   - Cultural differences in conversational pacing

2. **Maximum Duration**:
   - Already exists as `listen_duration`
   - Prevent infinite waiting
   - Control costs/resources

## Design Decision

### Parameter Names
- Keep `listen_duration` for backward compatibility (functions as max duration)
- Add `min_listen_duration` for consistency
- Both parameters in seconds (matching existing pattern)

### Behavior
- `min_listen_duration`: Minimum time to record before VAD can trigger stop
- `listen_duration`: Maximum time to record (existing parameter)
- VAD still detects silence, but respects minimum duration
- If `min_listen_duration` > `listen_duration`, use `listen_duration` (max wins)

### Implementation Details
1. Add `min_listen_duration` parameter to `converse()` and `listen_for_speech()` tools
2. Default to 0 (no minimum) for backward compatibility
3. Pass to recording functions alongside existing parameters
4. Modify VAD logic to respect minimum duration
5. Update documentation and tests

## Example Usage

```python
# Asking a complex question that needs thinking time
converse("What's your philosophy on life?", min_listen_duration=2.0, listen_duration=60.0)

# Quick yes/no question
converse("Do you like pizza?", min_listen_duration=0.5, listen_duration=10.0)

# Open-ended storytelling
converse("Tell me about your childhood", min_listen_duration=3.0, listen_duration=120.0)
```

## Implementation Checklist

- [ ] Add `min_listen_duration` parameter to tool schemas
- [ ] Update `record_audio_with_silence_detection()` to respect minimum
- [ ] Update `record_audio()` for consistency
- [ ] Add parameter validation
- [ ] Update documentation
- [ ] Add tests for new functionality
- [ ] Update CHANGELOG.md