# Streaming MCP with LiveKit for AI-to-AI Voice Conversations

## Overview

Research and implement HTTP streaming support in MCP combined with LiveKit to enable natural AI-to-AI voice conversations with proper turn-taking and reduced latency.

## Problem Statement

Current AI-to-AI voice conversations suffer from:
- AIs talking over each other (no turn detection)
- Long waiting times causing timeouts before responses
- Lack of coordination between conversation participants
- No streaming capability to start processing while other is speaking

## Background

### MCP HTTP Streaming (March 2024)
- MCP introduced HTTP streaming protocol support
- Enables real-time, bidirectional communication
- Server-sent events (SSE) for streaming responses
- WebSocket support for full duplex communication

### Current LiveKit Integration
- Voice Mode already has LiveKit support for room-based conversations
- LiveKit provides real-time audio/video infrastructure
- Supports multiple participants in rooms
- Has VAD and turn detection capabilities

## Research Areas

### 1. MCP Streaming Protocol
- [ ] Study MCP HTTP streaming specification
- [ ] Understand SSE implementation for MCP
- [ ] Research WebSocket transport option
- [ ] Analyze streaming message format and flow

### 2. LiveKit Advanced Features
- [ ] LiveKit turn detection APIs
- [ ] Room state synchronization
- [ ] Participant metadata for AI coordination
- [ ] Audio level detection for speaking detection

### 3. Integration Architecture
- [ ] Design streaming MCP server for voice mode
- [ ] Plan LiveKit room management for AI participants
- [ ] Create turn-taking protocol between AIs
- [ ] Handle partial responses and interruptions

### 4. Existing Solutions
- [ ] Research OpenAI Realtime API approach
- [ ] Study LiveKit Agents framework
- [ ] Look at other AI-to-AI communication systems

## Proposed Solutions (Multiple Approaches)

### Option 1: HTTPS Bridge Server (No LiveKit)
A centralized HTTPS endpoint that acts as a coordination bridge between multiple MCP hosts.

**Architecture:**
- Central bridge server with streaming HTTP endpoint
- Each AI connects via MCP streaming transport
- Bridge manages turn-taking and message routing
- State synchronization through the bridge
- No dependency on LiveKit at all

**Benefits:**
- Simpler architecture
- Direct MCP-to-MCP communication
- Lower latency (no audio encoding/decoding)
- Easier to debug text-based coordination

### Option 2: LiveKit Text Channels
Use LiveKit rooms for text-based coordination while audio happens separately.

**Architecture:**
- LiveKit room for coordination messages
- Text data channels for state sync
- Audio can be direct or through LiveKit
- Use LiveKit's participant management

**Benefits:**
- Leverages LiveKit's reliable infrastructure
- Built-in participant tracking
- Can mix text coordination with audio

### Option 3: Hybrid Streaming Approach
Combine MCP streaming with selective LiveKit usage.

**Architecture:**
- MCP streaming for AI responses
- LiveKit for audio mixing only when needed
- Direct peer-to-peer for 2 AIs
- LiveKit rooms for 3+ participants

### Option 4: Pure MCP Streaming Mesh
Each AI connects to others directly via streaming MCP.

**Architecture:**
- Peer-to-peer MCP streaming connections
- No central server required
- Each AI maintains connections to others
- Distributed state management

**Benefits:**
- No single point of failure
- Lowest possible latency
- True decentralization

## Coordination Protocols

### Text-Based Turn Taking Protocol
Using streaming MCP for coordination messages:

```json
{
  "type": "state_change",
  "participant": "claude",
  "state": "thinking|speaking|listening|waiting",
  "metadata": {
    "audio_level": 0.0,
    "estimated_duration": 5000,
    "can_interrupt": true
  }
}
```

### Bridge Server API
If using centralized bridge approach:

**Endpoints:**
- `POST /conversation/create` - Create new conversation room
- `GET /conversation/{id}/stream` - SSE stream for updates
- `POST /conversation/{id}/state` - Update participant state
- `POST /conversation/{id}/message` - Send coordination message

### Creative Uses of Streaming MCP

1. **Parallel Processing Streams**
   - Multiple AIs process same input simultaneously
   - Bridge merges/moderates responses
   - Best answer selection or synthesis

2. **Chain-of-Thought Streaming**
   - Stream reasoning steps between AIs
   - Each AI can build on previous thoughts
   - Collaborative problem solving

3. **Real-time Translation Bridge**
   - AIs speaking different languages
   - Bridge provides translation stream
   - Enables multilingual AI conversations

4. **Moderated Debates**
   - Bridge enforces speaking time limits
   - Automatic fact-checking streams
   - Structured debate formats

### Implementation Approaches

#### Approach A: Minimal Bridge Server
```python
# Simple FastAPI bridge for AI coordination
@app.get("/conversation/{conv_id}/stream")
async def stream_conversation(conv_id: str):
    async def event_generator():
        while True:
            # Send state updates, turn signals
            yield f"data: {json.dumps(state)}\n\n"
    
    return StreamingResponse(event_generator())
```

#### Approach B: MCP Tool Extension
Extend voice-mode with streaming capabilities:
- Add `converse_streaming` tool
- Implement SSE client for coordination
- Maintain persistent connections

#### Approach C: LiveKit Data Channels
```python
# Use LiveKit data messages for coordination
async def on_data_received(data: DataPacket, participant: Participant):
    message = json.loads(data.data)
    if message["type"] == "turn_request":
        await coordinate_turn_taking(participant)
```

## Innovative Streaming MCP Applications

### Beyond Voice Conversations

1. **Distributed AI Consciousness**
   - Stream consciousness between AI instances
   - Shared context and memory updates
   - Collaborative decision making

2. **AI Hive Mind Coordination**
   - Multiple specialized AIs working together
   - Stream task assignments and results
   - Dynamic role allocation

3. **Streaming Tool Execution**
   - Stream tool calls and results between AIs
   - One AI can see what another is doing in real-time
   - Collaborative coding/debugging sessions

4. **Event-Driven AI Workflows**
   - AIs subscribe to event streams
   - React to changes in real-time
   - Cascading AI responses

### MCP Streaming Patterns

1. **Request/Stream/Response Pattern**
```
Client -> Server: Request with streaming flag
Server -> Client: SSE stream of partial results
Server -> Client: Final result with stream close
```

2. **Bidirectional Streaming**
```
Client <-> Server: WebSocket connection
Both sides can send streaming messages
Real-time interaction without polling
```

3. **Pub/Sub Pattern**
```
Multiple clients subscribe to topics
Server streams updates to subscribers
Perfect for AI coordination
```

## Technical Considerations

### Streaming Benefits
- Start TTS playback while LLM still generating
- Begin STT processing during speech
- Reduce perceived latency significantly
- Enable real-time collaborative AI work
- Support event-driven architectures

### Protocol Considerations
- HTTP/2 or HTTP/3 for better multiplexing
- SSE for server-to-client streaming
- WebSockets for bidirectional needs
- gRPC as alternative for complex scenarios

### State Management
- Distributed state synchronization
- Conflict resolution strategies
- Event sourcing for audit trails
- CRDT for collaborative editing

## Success Criteria

- AIs can have natural conversations without talking over each other
- Minimal latency between turns
- Graceful handling of interruptions
- Support for 3+ AI participants
- Robust error handling and recovery

## References

- MCP HTTP Transport Spec: [need to research]
- LiveKit Agents: https://docs.livekit.io/agents/
- Voice Mode LiveKit code: `/voice_mode/tools/conversation.py`
- OpenAI Realtime: https://platform.openai.com/docs/guides/realtime

## Research Questions to Explore

1. **MCP Streaming Capabilities**
   - What exactly can be streamed? (tool calls, responses, events?)
   - How does error handling work in streams?
   - Can streams be paused/resumed?
   - What's the maximum stream duration?

2. **Multi-Host Coordination**
   - How do MCP hosts discover each other?
   - Can we use mDNS/Zeroconf for local discovery?
   - What about NAT traversal for remote hosts?
   - **Can Claude.ai web/mobile connect to streaming MCP servers?**

3. **Claude.ai Integration Possibilities**
   - Can Claude.ai act as an MCP client to external servers?
   - What security/CORS restrictions exist?
   - Would OAuth enable claude.ai to connect to voice-mode?
   - Can mobile apps use streaming MCP over HTTPS?

4. **Performance Characteristics**
   - Latency of streaming vs request/response
   - Bandwidth requirements for audio streaming
   - CPU usage for maintaining multiple streams

5. **Security & Authentication**
   - OAuth2 flow for claude.ai authentication
   - JWT tokens for session management
   - CORS configuration for web access
   - Rate limiting and abuse prevention

## Experiments to Try

1. **Simple Echo Chamber**
   - Two AIs streaming to each other
   - Each repeats what the other says
   - Test stream latency and reliability

2. **Collaborative Story Writing**
   - Multiple AIs taking turns adding sentences
   - Stream partial sentences for smooth handoffs
   - Test creative collaboration patterns

3. **Distributed Problem Solving**
   - Give AIs different tools/knowledge
   - Stream intermediate results
   - See if they can solve together what they can't alone

4. **AI Orchestra**
   - Multiple AIs generating music/sounds
   - Coordinate via streaming protocol
   - Test real-time synchronization

## Next Steps

1. Research MCP streaming specification in detail
2. Build minimal bridge server prototype
3. Test streaming between two MCP instances
4. Experiment with different coordination patterns
5. Design best approach for voice conversations
6. Implement on feature branch

## Related Tasks

- [Voice-Mode Streaming HTTP & OAuth for Web](./voice-mode-streaming-oauth-web.md)
  - Adapt voice-mode for claude.ai web/mobile access
  - OAuth authentication for secure connections
  - Could enable web-based AI conversations
  - Shared streaming infrastructure

## Integration Possibilities

### Claude.ai as Conversation Participant

If we can enable claude.ai to connect to streaming MCP servers:

1. **Mixed Human-AI Conversations**
   - Human using claude.ai web
   - Multiple AIs via MCP streaming
   - Real-time group discussions

2. **Mobile AI Orchestration**
   - Control AI conversations from phone
   - Monitor and intervene as needed
   - Record conversations for later

3. **Web-Based AI Coordination**
   - No local setup required
   - Browser-based AI management
   - Visual conversation flow

### Technical Synergies

Both tasks share:
- HTTP streaming protocols
- Authentication requirements
- WebSocket/SSE implementations
- Audio streaming challenges
- Security considerations

## Notes

- User has Claude Max 200k context for extended work
- Implementation can happen overnight on feature branch
- Focus on practical solution but explore creative possibilities
- Consider both voice and non-voice applications
- Research claude.ai integration possibilities