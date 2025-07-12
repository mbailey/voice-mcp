# Provider Registry

## Overview
Design and implementation of a provider registry system for Voice Mode that manages multiple TTS and STT providers with automatic fallback and cost optimization.

## Goals
- Support multiple TTS/STT providers (OpenAI, Kokoro, Whisper, etc.)
- Automatic provider selection based on availability
- Cost tracking and optimization
- Transparent failover between providers

## Status
MVP implementation complete. Enhancements ongoing.

## Files
- [design.md](./design.md) - Full provider registry architecture
- [mvp.md](./mvp.md) - MVP implementation plan
- Implementation notes in archive: [provider-registry-implementation.md](../archive/provider-registry-implementation.md)

## Key Features Implemented
- Basic registry with availability checking
- Provider selection logic
- Health check endpoints
- Automatic fallback chain