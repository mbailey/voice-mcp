# Wake Word Privacy Investigation

## Parent Task
This is a sub-task of [wake-word-detection.md](./wake-word-detection.md)

## Overview
Investigate technical and legal privacy considerations for wake word detection, with initial focus on AirPods Pro 2 behavior.

## Device-Specific Considerations

### AirPods Pro 2
- **Noise Cancellation**: Blocks external voices from being recorded
- **Transparency Mode**: May allow ambient sound through
- **Microphone Array**: Beam-forming focuses on wearer's voice
- **Privacy Advantage**: Natural protection against recording others
- **Testing Needed**: Verify isolation in different modes

### Other Devices to Document
- Standard headphones with boom mic
- Laptop/desktop microphones
- Smart speakers
- Mobile phone mics
- Jabra and other business headsets

## Legal Considerations

### Recording Laws by Jurisdiction
1. **One-Party Consent States/Countries**
   - Only one person needs to know about recording
   - Still ethical considerations for bystanders

2. **Two-Party Consent States/Countries**
   - All parties must consent to recording
   - Includes: California, Florida, Illinois, etc.
   - Stricter requirements

3. **Public vs Private Spaces**
   - Different rules for public areas
   - Workplace considerations
   - Home/personal space

### Best Practices
- Always disclose when using voice recording
- Implement "recording indicators"
- Provide clear opt-out mechanisms
- Document consent when required

## Technical Privacy Measures

### Local Processing First
- Wake word detection happens on-device
- No cloud transmission until activated
- Minimize data exposure

### Audio Isolation Techniques
1. **Directional Microphones**
   - Beam-forming to focus on speaker
   - Reduce ambient pickup

2. **Voice Activity Detection (VAD)**
   - Distinguish speaker from background
   - Filter non-speech audio

3. **Speaker Identification**
   - Only respond to enrolled voice
   - Additional privacy layer

### Buffer Management
- Circular buffer stays local
- Auto-purge after processing
- No persistent storage by default
- Optional logging with clear consent

## Implementation Recommendations

### For AirPods Pro 2 Users
```yaml
wake_word:
  device_profile: "airpods_pro_2"
  assume_isolated_audio: true
  privacy_mode: "strict"
  warn_on_transparency: true
```

### Privacy-First Features
1. **LED/Audio Indicators**
   - Visual: Status LED when possible
   - Audio: Subtle tone when activated
   - Haptic: For wearables

2. **Consent Management**
   - First-run privacy disclosure
   - Settings to disable features
   - Clear data deletion options

3. **Audit Logging**
   - When enabled, log activation times
   - No audio storage by default
   - User-controlled retention

## Research Tasks

### Technical Testing
- [ ] Test AirPods Pro 2 isolation in different modes
- [ ] Measure audio leakage with various devices
- [ ] Benchmark privacy-preserving VAD solutions
- [ ] Evaluate speaker identification accuracy

### Legal Research
- [ ] Compile recording law summary by region
- [ ] Create disclosure templates
- [ ] Review GDPR/CCPA implications
- [ ] Workplace recording policies

### User Experience
- [ ] Design privacy-first onboarding
- [ ] Create clear privacy documentation
- [ ] Develop consent UI/UX patterns
- [ ] Test user understanding of features

## Device Testing Matrix

| Device | Isolation | Legal Risk | Recommended Settings |
|--------|-----------|------------|---------------------|
| AirPods Pro 2 (NC) | High | Low | Default enabled |
| AirPods Pro 2 (Transparency) | Medium | Medium | Warning prompt |
| Laptop Mic | Low | High | Require explicit consent |
| Boom Mic Headset | Medium | Low | Default enabled |
| Speakerphone | None | High | Restricted mode |

## Privacy-Preserving Architecture

```
[Microphone] → [Local VAD] → [Wake Word Detection] → [User Confirmation] → [Cloud STT]
                     ↓                                          ↓
              [Local Buffer]                          [Privacy Indicator]
                     ↓
              [Auto-purge]
```

## Next Steps
1. Create test suite for AirPods Pro 2 isolation
2. Document findings for each device type
3. Build privacy indicator system
4. Implement consent management
5. Create user documentation
6. Consider privacy certification

## Open Questions
1. How to handle group settings appropriately?
2. Should we support "privacy zones" (geo-fencing)?
3. Integration with OS privacy controls?
4. How to handle mixed device scenarios?
5. Privacy implications of multiple wake words?

## Contributing
Device-specific experiences welcome! Please add sections for:
- Your device model and configuration
- Observed privacy behavior
- Recommended settings
- Any privacy concerns or benefits