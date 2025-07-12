# Wake Word Detection Feature

⚠️ **Status: Experimental - Not Yet Functional**

This feature is currently in development and not working properly. The code has been implemented but requires debugging and fixes before it can be used reliably.

## Overview
Implement always-listening mode with wake word detection for hands-free Voice Mode activation.

## Motivation
- Enable truly hands-free operation during activities (walking, cooking, etc.)
- Reduce friction for starting conversations
- Allow natural "Hey Claude" or custom wake word interactions
- Perfect for situations where pressing buttons is inconvenient

## Feature Description
Voice Mode MCP would continuously listen and buffer audio, only activating when it detects a configured wake word.

### Core Functionality
1. **Continuous Listening Mode**
   - Always listening but not always processing
   - Local wake word detection (privacy-focused)
   - Minimal resource usage when idle

2. **Buffer Management**
   - Rolling text buffer of recent transcriptions
   - Configurable buffer size (e.g., last 30 seconds)
   - Option to include pre-wake-word context

3. **Wake Word Options**
   - Default: "Hey Claude"
   - Custom wake words configurable
   - Multiple wake words support
   - Sensitivity adjustment

## Terminology
See [GLOSSARY.md](./GLOSSARY.md) for wake word feature terminology and interaction flows.

## State Management

### Conversation Modes
1. **Standby Mode**: Listening for wake word only
2. **Conversation Mode**: Active dialogue after wake word
3. **Idle Mode**: Not listening at all

### State Transitions
```
Idle -> Standby: User says "go into standby mode"
Standby -> Conversation: Wake word detected
Conversation -> Standby: Based on VOICE_MODE_STANDBY setting
Conversation -> Idle: User says "exit standby mode"
```

### Environment Variables
```yaml
VOICE_MODE_STANDBY: "auto"  # on, off, auto
  # on: Always return to standby after conversation
  # off: Never auto-return to standby
  # auto: Smart detection (goodbye phrases, extended silence)

VOICE_MODE_DEFAULT_STATE: "standby"  # standby or idle
  # For accessibility users who need always-on voice

VOICE_MODE_WAKE_CONTEXT_SECONDS: 10
  # Seconds of pre-wake-word context to include
```

## Context Management

### Initial Context Sharing
- Default: Include 10 seconds before wake word
- Minimal privacy exposure
- Sufficient for most requests

### Additional Context Tool
```python
# Separate tool requiring permission
request_conversation_history(
    minutes=2,
    reason="Need context about shopping prices discussion"
)
# User sees: "Claude requests last 2 minutes of conversation about shopping prices"
# User can approve/deny with visibility into content
```

### Sentence Boundary Detection
- After wake word, collect until sentence end
- Use punctuation (. ? !) as boundaries
- Fallback to 2+ second silence
- Prevents mid-thought cutoffs

## Implementation Approaches

### Option 1: Integrated into `converse()` tool (Preferred for MVP)
```python
converse(
    message="",
    wait_for_wake_word=True,
    wake_word="Hey Claude",
    include_buffer=True,
    buffer_seconds=10
)
```

### Option 2: Separate `listen_for_wake_word()` tool
```python
# Returns when wake word detected
context = listen_for_wake_word(
    wake_word="Hey Claude",
    return_buffer=True
)
# Then use regular converse
converse(message=context)
```

### Option 3: Background service mode
- Separate process monitoring for wake words
- Triggers regular converse when detected
- More complex but most responsive

## Technical Considerations

### Privacy & Performance
- All processing happens locally
- Use efficient wake word detection library
- Consider using WebRTC VAD for efficiency
- Option to disable cloud STT until wake word detected

### Wake Word Detection Libraries
1. **Porcupine** - Offline, cross-platform, accurate
2. **Snowboy** - Discontinued but forks exist
3. **OpenWakeWord** - Open source, actively maintained
4. **Vosk** - Includes wake word capabilities
5. **SpeechRecognition** with keyword spotting

### Buffer Strategy
- Continuous local STT with circular buffer
- Only send to LLM after wake word
- Option to include N seconds before wake word
- Clear buffer after processing

### Conversation Awareness
- **Challenge**: During conversations, user's silence while others speak creates hallucination risk
- **Solution**: Implement conversation detection to handle turn-taking
- **Smart Segmentation**: Adjust chunk size based on speech patterns
- **Hallucination Filtering**: Critical for multi-person scenarios
- See [ASR Hallucination Prevention](./asr-hallucination-prevention.md) for details

## User Experience

### Configuration
```yaml
wake_word:
  enabled: true
  phrases: ["Hey Claude", "OK Claude", "Claude"]
  sensitivity: 0.5
  buffer_seconds: 10
  include_pre_context: true
```

### Usage Examples
1. **Dog Walking**: "Hey Claude, remind me to buy dog food"
2. **Cooking**: "OK Claude, how long for medium-rare steak?"
3. **Driving**: "Claude, what's the weather tomorrow?"
4. **Working**: "Hey Claude, create a git commit for these changes"

## Privacy Considerations
- Wake word detection happens entirely locally
- No audio sent to cloud until wake word detected
- Optional: LED/sound indicator when listening
- Clear documentation about data handling

## Integration with Existing Features
- Works with all existing voice modes
- Compatible with transport options (local/LiveKit)
- Respects audio feedback settings
- Can trigger any voice conversation type

## Success Metrics
- Wake word detection accuracy > 95%
- False positive rate < 1%
- Response latency < 500ms after wake word
- CPU usage < 5% when idle

## Next Steps
1. Research and test wake word detection libraries
2. Prototype basic implementation
3. Test CPU/memory usage patterns
4. Design configuration interface
5. Implement buffer management
6. Add privacy indicators
7. Create documentation and examples

## Related Features
- Could enable "conversation mode" where it stays active
- Multiple wake words for different contexts
- Wake word training for custom voices
- Integration with home automation

## Total Recall Mode - Life Logging Extension

### Vision
Transform standby mode into a comprehensive life logging tool that creates a searchable archive of everything spoken.

### Core Concept
- Continuous transcription and archival of all speech
- Not just wake word detection, but complete spoken history
- "Total Recall" of conversations, thoughts, ideas
- Searchable database of your verbal life

### Implementation Details

#### Storage Architecture
```yaml
storage:
  mode: "total_recall"  # ephemeral, session, total_recall
  retention: "permanent"  # or days/weeks/months
  format: "daily_files"  # YYYY-MM-DD-transcripts.jsonl
  encryption: true
  compression: true
  location: "~/.voicemode/life_log/"
```

#### Daily File Format
```json
{
  "timestamp": "2025-07-06T14:32:15Z",
  "audio_file": "optional/path/to/audio.wav",
  "transcription": "Hey Claude, remind me to buy milk",
  "wake_word_detected": true,
  "context": {
    "location": "walking_route_a",
    "activity": "dog_walk",
    "device": "airpods_pro_2"
  }
}
```

#### Privacy & Control
- **Pause Command**: "Hey Claude, pause recording for 10 minutes"
- **Delete Command**: "Delete the last hour of recordings"
- **Privacy Zones**: GPS-based auto-pause in sensitive locations
- **Encryption**: All files encrypted at rest
- **Export**: Easy export for backup or analysis

#### Search & Retrieval
- Full-text search across all transcriptions
- Time-based queries: "What did I say about X last Tuesday?"
- Context queries: "Find all conversations during dog walks"
- Idea extraction: "Show me all my startup ideas"

#### Use Cases
1. **Memory Augmentation**: "What was that idea I had yesterday?"
2. **Meeting Recall**: "What did I promise Chris at the park?"
3. **Personal Growth**: Review communication patterns
4. **Idea Capture**: Never lose a shower thought again
5. **Memoir Writing**: Source material for life stories

#### Storage Estimates
- Average speaking: ~150 words/minute
- Active talking: ~2 hours/day
- Daily storage: ~18,000 words ≈ 100KB compressed
- Yearly storage: ~36MB text (very manageable)
- With audio: ~2GB/year at compressed rates

### Configuration Example
```yaml
total_recall:
  enabled: true
  store_audio: false  # Just transcriptions to save space
  store_transcriptions: true
  encryption_key: "path/to/key"
  auto_backup: "daily"
  backup_location: "cloud/provider"
  privacy_zones:
    - location: "home"
      action: "continue"  # Still record at home
    - location: "doctor_office"
      action: "pause"    # Auto-pause in medical settings
  search_index: true
  export_formats: ["json", "markdown", "csv"]
```

### Future Enhancements
- AI summaries of each day/week/month
- Automatic extraction of action items
- Sentiment analysis over time
- Integration with other life logging tools
- Voice journal prompts based on patterns

## Open Questions
1. Should wake word be processed locally only?
2. How to handle multiple simultaneous speakers?
3. Battery impact on mobile devices?
4. Integration with OS-level assistants?
5. Custom wake word training interface?
6. Legal implications of Total Recall mode?
7. How to handle storage growth over years?
8. Should audio be retained or just transcriptions?