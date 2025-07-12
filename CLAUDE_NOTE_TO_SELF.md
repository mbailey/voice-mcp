# CLAUDE_NOTE_TO_SELF.md

- This file contain important context from previous sessions
- Before context window clearing, Claude adds notes to this file
- Read them to understand ongoing work and next steps

## The notes

2025-07-06

- We've been working on docs/tasks/wake-word-detection/
- wait_for_wake_word isn't detecting "Hey Claude"
- We're noticed 6.7 second audio recording being sent to local whisper
- Reorganized docs/tasks/ to conform with TASK-MANAGEMENT.md:
  - All tasks now have their own directories
  - Moved standalone .md files into task-name/README.md format
  - Updated all links in docs/tasks/README.md
  - Key files that remain in root: GLOSSARY.md, INSIGHTS.md, TASK-MANAGEMENT.md, implementation-notes.md, key-insights.md
  - Current symlink points to wake-word-detection task

