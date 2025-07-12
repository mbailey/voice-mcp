# Wake Word Feature Implementation Plan

## Overview
Implement standby mode with wake word detection for hands-free Voice Mode operation.

## Phase 1: Basic Wake Word Detection (Week 1)

### Milestone 1.1: Local Command Detection
- [ ] Add wake word detection library (start with vosk or pocketsphinx)
- [ ] Create basic detection for "Hey Claude"
- [ ] Test accuracy and false positive rate
- [ ] Add audio feedback on detection (beep/chime)

### Milestone 1.2: Integrate with Converse Tool
- [ ] Add `wait_for_wake_word` parameter to converse()
- [ ] Implement basic standby mode entry/exit
- [ ] Create state management (idle/standby/active)
- [ ] Add "stand down" and "standby" commands for pause/resume

### Milestone 1.3: Configuration System
- [ ] Add environment variables:
  - `VOICE_MODE_WAKE_WORD` (default: "Hey Claude")
  - `VOICE_MODE_STANDBY` (default: "off")
  - `VOICE_MODE_PAUSE_COMMAND` (default: "stand down")
  - `VOICE_MODE_RESUME_COMMAND` (default: "standby")
- [ ] Create configuration validation
- [ ] Document configuration options

## Phase 2: Continuous Transcription Loop (Week 2)

### Milestone 2.1: Audio Chunking System
- [ ] Implement 5-second audio chunk recording
- [ ] Create circular buffer for audio segments
- [ ] Add timestamp tracking for each chunk
- [ ] Handle chunk overlap for seamless detection

### Milestone 2.2: Local STT Integration
- [ ] Force local Whisper endpoint for standby mode
- [ ] Implement continuous transcription pipeline
- [ ] Create text buffer management
- [ ] Add memory-efficient circular text buffer

### Milestone 2.3: Wake Word Text Detection
- [ ] Scan transcribed text for wake words
- [ ] Handle partial wake words across chunks
- [ ] Implement sentence boundary detection
- [ ] Extract complete utterance after wake word

## Phase 3: Context Management (Week 3)

### Milestone 3.1: Pre-Wake Context
- [ ] Implement configurable context window (default 10 seconds)
- [ ] Create context extraction from buffer
- [ ] Add `VOICE_MODE_WAKE_CONTEXT_SECONDS` variable
- [ ] Test context relevance and privacy

### Milestone 3.2: Conversation Mode
- [ ] Implement state transition to conversation mode
- [ ] Disable wake word detection during conversations
- [ ] Add return-to-standby logic based on settings
- [ ] Implement timeout handling

### Milestone 3.3: Permission-Based History
- [ ] Create `request_conversation_history()` tool
- [ ] Implement permission prompt system
- [ ] Add content preview for approval
- [ ] Create audit logging for history requests

## Phase 4: Privacy & Storage (Week 4)

### Milestone 4.1: Local Privacy Controls
- [ ] Implement "stand down" command interception
- [ ] Add immediate recording stop capability
- [ ] Create privacy indicator system
- [ ] Add configurable privacy zones

### Milestone 4.2: Total Recall Storage (Optional)
- [ ] Create GPG encryption pipeline
- [ ] Implement YubiKey integration
- [ ] Design daily file storage format
- [ ] Build search indexing system
- [ ] Create secure backup mechanism

### Milestone 4.3: ASR Hallucination Prevention
- [ ] Implement VAD pre-filtering
- [ ] Add hallucination pattern detection
- [ ] Create confidence thresholding
- [ ] Filter common false phrases

## Phase 5: Testing & Refinement (Week 5)

### Milestone 5.1: Real-World Testing
- [ ] Test with AirPods Pro 2 in various modes
- [ ] Verify conversation isolation
- [ ] Test in noisy environments
- [ ] Validate battery impact

### Milestone 5.2: Performance Optimization
- [ ] Optimize CPU usage in standby
- [ ] Reduce memory footprint
- [ ] Improve wake word accuracy
- [ ] Minimize latency

### Milestone 5.3: Documentation
- [ ] Create user guide
- [ ] Document privacy features
- [ ] Add troubleshooting guide
- [ ] Create demo videos

## Success Criteria

### Functionality
- Wake word detection accuracy > 95%
- False positive rate < 1%
- Response latency < 500ms
- CPU usage < 5% in standby

### Privacy
- All transcription happens locally in standby
- Clear privacy indicators
- Immediate stop capability
- No cloud data in standby mode

### Usability
- Works seamlessly with AirPods Pro 2
- Natural conversation flow
- Configurable for different users
- Accessible for vision-impaired users

## Technical Decisions

### Wake Word Detection Library
**Decision**: Start with Vosk
- Pros: Offline, lightweight, good accuracy
- Cons: Limited customization
- Alternative: Pocketsphinx if Vosk insufficient

### Audio Processing
**Decision**: 5-second chunks with 0.5s overlap
- Balances latency and accuracy
- Prevents cutting wake words
- Manageable memory usage

### Storage Format
**Decision**: JSONL with daily rotation
- Human-readable
- Efficient for append operations
- Easy to compress and encrypt

## Risk Mitigation

### Risk: High CPU usage
**Mitigation**: Implement aggressive VAD, optimize chunk size

### Risk: Privacy concerns
**Mitigation**: Local-only by default, clear documentation

### Risk: Poor accuracy in noise
**Mitigation**: Multiple wake word models, confidence tuning

## Next Steps
1. Set up development environment with Vosk
2. Create basic wake word detection prototype
3. Test with various microphones
4. Begin integration with converse tool

## Notes
- Priority is MVP functionality over features
- Privacy-first design throughout
- Optimize for AirPods Pro 2 use case
- Keep Total Recall as optional enhancement