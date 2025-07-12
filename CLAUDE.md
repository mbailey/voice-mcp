# Instructions for Claude

@README.md : Project overview
@GLOSSARY.md : Defines terms used in this project
@INSIGHTS.md : Insights uncovered while working on this project
@.repos.txt : 3rd party git repos
@docs/tasks/README.md : Always update this with link to the current tasks
@docs/tasks/current/README.md : Always symlink `current` to the current task before restart

## Wake-Up Protocol

1. @CLAUDE_CONTEXT contains important context from previous sessions
2. Read it to understand ongoing work and next steps
3. Write to it before context is to be cleared (e.g. before being restarted)

## Primary Directive

ALWAYS read the following files at the start of any session:
- docs/tasks/implementation-notes.md # Important implementation decisions and fixes

## Context-Aware Loading

Load specific convention modules based on the current work context:

- **Editing bash scripts**: Load `docs/conventions/core/principles.md` + `.conventions/languages/bash.md` + `.conventions/interfaces/cli.md`
- **Python development**: Load `docs/conventions/core/principles.md` + `.conventions/languages/python.md` + `.conventions/interfaces/cli.md`
- **Writing documentation**: Load `docs/conventions/core/principles.md` + `.conventions/core/documentation.md` + `.conventions/languages/markdown.md`
- **General project work**: Load docs/conventions.md` + `.conventions/core/project-structure.md`

## Task Management

When working on voice-mode features:
1. Check `docs/tasks/` directory for current work and plans
2. Key files in docs/tasks/:
   - `README.md` - Task list and completed features
   - `provider-registry-design.md` - Full provider registry architecture
   - `provider-registry-mvp.md` - MVP implementation plan
   - `emotional-tts-plan.md` - Emotional TTS feature design
   - `implementation-notes.md` - Completed work and decisions
   - `key-insights.md` - Important learnings

## Voice Stack Overview

The voice-mode project now has a complete local voice processing stack:

### Services
- **Whisper.cpp STT** (Port 2022): Local speech-to-text with OpenAI-compatible API
- **Kokoro TTS** (Port 8880): Local text-to-speech with OpenAI-compatible API  
- **LiveKit** (Port 7880): Real-time voice orchestration
- **Voice Frontend** (Port 3001): User interface for voice interactions

### Key Commands
- `mt sync` - Download external repositories
- `make install` - Install and build all components
- `make dev` - Start complete voice stack
- `make whisper-start/stop` - Manage Whisper STT
- `make kokoro-start/stop` - Manage Kokoro TTS

### Architecture Notes
- Whisper runs as native binary (no container) for performance
- Kokoro runs in container for dependency isolation
- Both services expose OpenAI-compatible APIs
- Automatic fallback from local to cloud services
- Hardware detection for optimal model selection

## Important Notes

- These conventions are personal preferences, not rigid rules
- Adapt suggestions to fit the specific project context
- When in doubt, ask for clarification rather than assume

# important-instruction-reminders
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.

## OpenAI API Usage
- Use OpenAI API whenever possible as self hosted alternatives support it and we can use them by setting OPENAI_BASE_URL

## Kokoro TTS Management Prompts

### kokoro-start
When the user asks to "start kokoro", "enable kokoro", "turn on kokoro", "use local TTS", or similar:
- Use the `mcp__voice-mode__kokoro_start` tool
- The tool will start the Kokoro TTS service on port 8880
- Optional: specify a custom models directory path (defaults to ~/Models/kokoro)
- After starting, inform the user that Kokoro is now running and ready for local TTS

### kokoro-stop  
When the user asks to "stop kokoro", "disable kokoro", "turn off kokoro", or similar:
- Use the `mcp__voice-mode__kokoro_stop` tool
- The tool will gracefully terminate the Kokoro TTS service
- Inform the user that Kokoro has been stopped

### kokoro-status
When the user asks "is kokoro running?", "kokoro status", "check kokoro", or similar:
- Use the `mcp__voice-mode__kokoro_status` tool
- The tool will check if Kokoro is running and provide process details
- Report the status to the user including CPU/memory usage if available

## Git Workflow Reminders
- Review and update CHANGELOG before each git commit
