# Voice-Mode Tasks and Ideas

## Documentation

@TASK-MANAGEMENT.md explains how to manage tasks and documentation
- [Implementation Notes](./implementation-notes.md) - Completed work and decisions
- [Key Insights](./key-insights.md) - Important learnings and design principles
- [Screencasts](./screencasts/README.md) - Video production plans and scripts
- [Screencast Quickstart](./screencast-quickstart/README.md) - Quick video creation guide and runbook

## The One Thing

- [ ] [Wake Word Detection](./wake-word-detection/README.md) - Always-listening mode with "Hey Claude" activation for hands-free operation
- [ ] [Claude.ai Web + LiveKit iOS Bridge](./claude-web-livekit-mobile-bridge/README.md) - Speak to Claude.ai through LiveKit iOS app

## High Priority

- [ ] [Voice Preferences System](./voice-preferences-system/README.md) - Set default voices per project/user/machine
- [ ] [Create Screencast](./screencast-quickstart/README.md) - Make 2-minute quickstart video demonstrating voice-mode
- [ ] [Conversation Browser Improvements](./conversation-browser/README.md) - Group exchanges into conversations, better UI
- [ ] Context Prime Optimization - Make /context-prime command super fast
- [ ] Enhance provider registry with cost/latency/privacy metadata
- [ ] Fix MCP timing issues with silence detection (VAD works in standalone but has delays through MCP)

## Medium Priority

- [ ] Fix metrics attribution in JSONL logs - STT metrics should appear on user utterances, TTS metrics on assistant utterances
- [ ] Add inline audio players to conversation browser - click to play audio without leaving the page
- [ ] Provider selection logic based on user preferences (cost, privacy, features)
- [ ] Automatic fallback chain for providers
- [ ] Better first-run experience for Kokoro model downloads
- [ ] Configuration documentation update for new unified system

## Low Priority

- [ ] Provider cost tracking and reporting
- [ ] Audio/transcription manifest files linking recordings with metadata
- [ ] Conversation export features (for podcasts, analysis)
- [ ] Provider capability matrix display
- [ ] Add MCP resources for setup guides and troubleshooting (platform-specific instructions)

## Ideas to Explore

- Look at OpenRouter's model for presenting provider options with transparent pricing
- Consider download size as a provider property for local models
- Add provider quality ratings based on user feedback
- Support for provider-specific features (emotions, voice cloning, etc.)

## Future Vision

- [ ] [Streaming MCP with LiveKit for AI Conversations](./streaming-mcp-livekit/README.md) - Enable natural AI-to-AI voice conversations using HTTP streaming
- [ ] [Voice-Mode Streaming HTTP & OAuth for Web](./voice-mode-streaming-oauth-web/README.md) - Enable claude.ai web/mobile to connect to voice-mode

## Inbox (New Ideas to Review)

- [ ] In-memory buffer for conversation timing metrics
  - Track full conversation lifecycle including Claude response times
  - Maintain recent interaction history without persistent storage
- [ ] Sentence-based TTS streaming
  - Send first sentence to TTS immediately while rest is being generated
  - Significant reduction in time to first audio (TTFA)
- [ ] Persistent settings file for voice-mode
  - Allow Claude to modify user preferences
  - Include: silence threshold, VAD aggressiveness, preferred voices
  - Respect security boundaries (some env vars remain read-only)
- [ ] LiveKit integration improvements
  - Complete integration for room-based conversations
  - iOS app setup for mobile voice interactions
- [ ] Streaming HTTP version for voice interactions
- [ ] Fix Kokoro authentication with OpenAI client
  - Currently works via curl but fails through AsyncOpenAI client
  - May need special handling for local endpoints
- [ ] Implement proper debug logging with trace mode
  - Add VOICEMODE_DEBUG=trace option for verbose HTTP logging
  - Enable httpx and openai library debug logging
  - Write debug logs to ~/.voicemode/logs/debug/voicemode_debug_YYYY-MM-DD.log
  - Essential for troubleshooting provider connection issues
- [ ] Multi-agent coordination via LiveKit rooms ("Minions")
  - Agents on different computers connect to shared LiveKit room
  - Voice-based inter-agent communication and coordination
  - Distributed task management and status sharing
  - Failover and load balancing capabilities
  - Like Despicable Me minions but for system administration

## Recently Completed

- [x] Audio format configuration - PCM as default for TTS streaming (better than Opus for streaming)
  - [Implementation Notes](./archive/audio-format-implementation.md)
- [x] Provider Registry MVP - Basic registry with availability checking and selection logic
  - [Design Document](./provider-registry/design.md)
  - [MVP Implementation](./provider-registry/mvp.md)
  - [Implementation Notes](./archive/provider-registry-implementation.md)
- [x] Silence detection implementation - WebRTC VAD for automatic recording stop
  - [Design Document](./silence-detection/design.md)
  - [Implementation Notes](./silence-detection/implementation.md)
- [x] Update default voices - alloy for OpenAI, af_sky for Kokoro
- [x] Unified voice service status tool
- [x] Auto-start Kokoro functionality
- [x] Fixed health check endpoints for whisper.cpp and Kokoro
- [x] Emotional TTS with cost controls (VOICE_ALLOW_EMOTIONS)
- [x] Fixed OpenAI TTS client initialization bug
- [x] Min/Max duration control for voice responses
  - Added `min_listen_duration` parameter to prevent premature cutoffs
  - [Implementation Details](./min-max-duration-control/README.md)

## Current Branches

- `master` - Has unified status tool and auto-start
- `feature/wake-word-detection` - Wake word detection feature (current)
- `feature/provider-registry` - Provider registry design docs
- `feature/emotional-tts` - Emotional TTS implementation (merged fixes)
- `feature/response-duration-min-max` - Min/max duration control (implemented)
