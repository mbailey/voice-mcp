# Silence Detection

## Overview
Implementation of WebRTC VAD (Voice Activity Detection) for automatic recording stop when user finishes speaking.

## Goals
- Eliminate need for manual stop or fixed duration recordings
- Improve conversation flow with natural pauses
- Reduce latency by stopping as soon as user is done

## Status
Implementation complete but has known MCP timing issues.

## Files
- [design.md](./design.md) - Initial design and specification
- [implementation.md](./implementation.md) - Implementation notes and decisions

## Known Issues
- VAD works well in standalone mode but has delays when used through MCP
- May need tuning for different environments/microphones