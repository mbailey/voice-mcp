# MCP Server Resilience Task

## Problem
The Voice Mode MCP server fails/crashes when:
- User hits Escape key during operation
- Network connection issues occur
- Other unexpected interruptions

Additionally, silent failures occur where:
- TTS (text-to-speech) continues working
- STT (speech-to-text) silently fails
- No audio recorded OR audio recorded but STT API fails
- No error messages shown to user

This requires restarting Claude/the MCP client, which disrupts workflow.

## Symptoms
- MCP server becomes unresponsive
- Voice mode tools stop working
- Need to restart Claude to restore functionality

## Investigation Areas
1. Error handling in the MCP server main loop
2. Signal handling (SIGINT, SIGTERM, etc.)
3. Network timeout and reconnection logic
4. Graceful degradation when services unavailable
5. STT failure detection and reporting
6. Check if WAV files are created during "no speech detected" periods
7. Add logging to distinguish recording failures vs STT API failures

## Potential Solutions
- Add robust exception handling around all MCP operations
- Implement automatic reconnection logic
- Add health check endpoint that clients can poll
- Better cleanup of resources on interruption
- Consider supervisor process or systemd-style restart

## Priority
Medium-High - This affects daily usability and user experience

## Notes
- Issue reported during voice conversation on 2025-07-02
- Escape key interruption is particularly common use case