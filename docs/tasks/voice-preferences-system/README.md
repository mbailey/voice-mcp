# Voice Preferences System

## Overview

Implement a system for setting voice preferences that can be defined at the project or user level, providing automatic voice selection based on directory context.

## Use Cases

1. **Personal Preferences**: User prefers "nova" voice globally
2. **Work Projects**: Use professional "alloy" voice for work repositories
3. **Demo Projects**: Use specific voices for demo/presentation directories
4. **Project-specific**: Each project can have its own preferred voice

## Implementation Specification

### File Format

- **Filename**: `voices.txt`
- **Location**: Inside `.voicemode/` directory
- **Format**: Simple text file with one voice name per line
- **Example**:
  ```
  nova
  shimmer
  alloy
  echo
  ```

### Discovery Logic

1. Start from current working directory
2. Walk up directory tree checking each level for `.voicemode/voices.txt`
3. Stop at first file found (do not merge multiple files)
4. If no file found in project tree, check `~/.voicemode/voices.txt`
5. Use only ONE file - the first one found

### Preference Order

When selecting a voice, the system will use this priority:
1. **Explicit parameter**: If voice specified in `converse()` call
2. **Preferences file**: Voices from the discovered `voices` file
3. **Environment variable**: Voices from `VOICEMODE_TTS_VOICES`
4. **Built-in defaults**: System default voice list

The preferences are PREPENDED to the default list, not replacing it. This ensures fallback to defaults if preferred voices are unavailable.

### Caching

- Load preferences once per session (when server starts)
- Cache the discovered voice list to avoid repeated file lookups
- Use the same voice throughout the session for consistency
- Allow override via explicit voice parameter

### Integration Points

- Modify provider selection logic to prepend user preferences
- Update `get_tts_client_and_voice()` to check preferences
- Add logging to show which preferences file was loaded
- Cache preferences at module or server level

## Implementation Tasks

- [ ] Design config file format and schema
- [ ] Implement config file discovery and loading
- [ ] Add preference resolution logic
- [ ] Integrate with existing voice selection
- [ ] Add CLI commands for managing preferences
- [ ] Document the feature
- [ ] Add tests for preference loading and resolution

## Security Considerations

- Config files should not contain API keys
- Validate voice names against allowed list
- Consider file permissions on config files

## Future Enhancements

- GUI preference editor
- Voice preview/test command
- Per-application preferences (different voice for different LLM tools)
- Time-based rules (different voice for morning/evening)
- Mood-based selection