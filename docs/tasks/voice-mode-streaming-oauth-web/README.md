# Voice-Mode Streaming HTTP & OAuth for Web Access

## Overview

Adapt voice-mode to support HTTP streaming and OAuth authentication, enabling users to connect from claude.ai web interface and mobile apps directly to their local or cloud-hosted voice-mode instances.

## Vision

Users could:
1. Run voice-mode locally or on a cloud server
2. Visit claude.ai and authenticate with their voice-mode instance
3. Have voice conversations through the web browser
4. Use mobile apps to connect to their personal voice-mode server

## Architecture Considerations

### Current Limitations
- Voice-mode runs as local MCP server (stdio transport)
- No built-in web server or HTTP API
- No authentication mechanism
- Browser security (CORS, secure contexts)

### Proposed Architecture

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│  Claude.ai Web  │◄────────┤  Voice-Mode      │◄────────┤  Local Audio    │
│  or Mobile App  │  HTTPS  │  Streaming Server│  Local  │  Devices        │
└─────────────────┘         └──────────────────┘         └─────────────────┘
        │                            │
        │                            │
        ▼                            ▼
┌─────────────────┐         ┌──────────────────┐
│  OAuth Provider │         │  MCP Tools &     │
│  (Auth0/Custom) │         │  Resources       │
└─────────────────┘         └──────────────────┘
```

## Implementation Approaches

### Option 1: Voice-Mode as Web Service

Transform voice-mode into a web service with streaming endpoints:

**Components:**
- FastAPI/Flask web server with streaming support
- OAuth2 authentication (Auth0, Okta, or custom)
- WebRTC for browser audio capture
- SSE/WebSocket for streaming responses
- HTTPS with proper certificates

**Endpoints:**
```
POST /auth/login          - OAuth flow initiation
GET  /auth/callback       - OAuth callback
GET  /api/stream          - SSE endpoint for AI responses
POST /api/audio           - Upload audio for STT
GET  /api/audio/stream    - Stream TTS audio
WS   /api/conversation    - WebSocket for full duplex
```

### Option 2: MCP-over-HTTP Bridge

Create a bridge that exposes MCP tools via HTTP:

**Architecture:**
- Thin HTTP server that translates to MCP
- Maintains MCP server connection locally
- Streams MCP responses over HTTP
- OAuth protects the HTTP endpoints

**Benefits:**
- Minimal changes to existing voice-mode
- Can work with any MCP server
- Clear separation of concerns

### Option 3: Browser Extension Bridge

Use a browser extension as a secure bridge:

**Components:**
- Browser extension with native messaging
- Local bridge service
- Secure communication channel
- No CORS issues

**Flow:**
1. User installs browser extension
2. Extension connects to local voice-mode
3. Claude.ai communicates through extension
4. Extension handles audio permissions

## Technical Requirements

### Authentication & Security

1. **OAuth2 Implementation**
   ```python
   from fastapi import FastAPI, Depends
   from fastapi.security import OAuth2PasswordBearer
   
   oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
   
   @app.get("/api/protected")
   async def protected_route(token: str = Depends(oauth2_scheme)):
       # Verify JWT token
       user = verify_token(token)
       return {"user": user}
   ```

2. **CORS Configuration**
   ```python
   from fastapi.middleware.cors import CORSMiddleware
   
   app.add_middleware(
       CORSMiddleware,
       allow_origins=["https://claude.ai"],
       allow_credentials=True,
       allow_methods=["*"],
       allow_headers=["*"],
   )
   ```

3. **HTTPS Requirements**
   - Valid SSL certificate (Let's Encrypt)
   - Secure WebSocket (WSS)
   - Secure contexts for audio access

### Audio Handling in Browser

1. **WebRTC Audio Capture**
   ```javascript
   navigator.mediaDevices.getUserMedia({ audio: true })
     .then(stream => {
       // Process audio stream
       const mediaRecorder = new MediaRecorder(stream);
       mediaRecorder.ondataavailable = handleAudioData;
     });
   ```

2. **Audio Streaming**
   - Chunked audio upload for STT
   - Server-sent events for TTS
   - Low-latency audio playback

### MCP Streaming Integration

1. **SSE for MCP Responses**
   ```python
   @app.get("/api/mcp/stream")
   async def mcp_stream(request: Request):
       async def generate():
           async for message in mcp_client.stream():
               yield f"data: {json.dumps(message)}\n\n"
       
       return StreamingResponse(generate(), media_type="text/event-stream")
   ```

2. **WebSocket for Bidirectional**
   ```python
   @app.websocket("/ws")
   async def websocket_endpoint(websocket: WebSocket):
       await websocket.accept()
       # Handle bidirectional MCP communication
   ```

## Claude.ai Integration Research

### Key Questions

1. **Can Claude.ai connect to external services?**
   - Current limitations on external API calls
   - Possibility of whitelisted domains
   - Custom integration requirements

2. **Mobile App Capabilities**
   - Can mobile apps make HTTPS requests?
   - Audio recording permissions
   - Background operation support

3. **Authentication Flow**
   - How would users link their accounts?
   - Token storage and refresh
   - Security implications

### Potential Integration Points

1. **Custom Claude Project**
   - Configure project to use external tools
   - MCP-over-HTTP as tool provider
   - OAuth token in project config

2. **Share Links**
   - Generate shareable links with auth
   - Time-limited access tokens
   - Voice conversation sessions

3. **Webhook Integration**
   - Claude.ai sends webhooks to voice-mode
   - Voice-mode responds with audio
   - Async conversation flow

## Privacy & Security Considerations

1. **Data Flow**
   - Audio never stored permanently
   - End-to-end encryption options
   - User controls all data

2. **Authentication**
   - OAuth2 with refresh tokens
   - Optional API key authentication
   - Rate limiting per user

3. **Deployment Options**
   - Self-hosted (full control)
   - Cloud hosted (convenience)
   - Hybrid (local audio, cloud coordination)

## Implementation Roadmap

### Phase 1: HTTP API Foundation
- [ ] Create FastAPI wrapper for voice-mode
- [ ] Implement basic HTTP endpoints
- [ ] Add SSE streaming support
- [ ] Test with curl/Postman

### Phase 2: Authentication
- [ ] Implement OAuth2 flow
- [ ] Add JWT token validation
- [ ] Create user management
- [ ] Test security measures

### Phase 3: Web Audio
- [ ] WebRTC audio capture
- [ ] Audio streaming protocols
- [ ] Browser compatibility testing
- [ ] Optimize latency

### Phase 4: Claude.ai Research
- [ ] Test API connectivity options
- [ ] Investigate integration methods
- [ ] Document limitations
- [ ] Propose solutions

### Phase 5: Production Ready
- [ ] HTTPS setup guide
- [ ] Docker deployment
- [ ] Security hardening
- [ ] Performance optimization

## Alternative Approaches

### 1. Progressive Web App (PWA)
- Standalone voice-mode PWA
- Connects to Claude.ai via API
- Installable on mobile devices
- Offline capability

### 2. WebRTC Peer Connection
- Direct browser-to-browser audio
- No server-side audio processing
- Lower latency potential
- More complex NAT traversal

### 3. Federation Protocol
- Multiple voice-mode instances
- Federated authentication
- Decentralized architecture
- ActivityPub-style protocol

## Questions for Exploration

1. What are the exact capabilities of claude.ai for external connections?
2. Can mobile apps maintain persistent connections?
3. What's the best audio codec for web streaming?
4. How to handle network interruptions gracefully?
5. Can we use WebTransport for better performance?

## Related Tasks

- [Streaming MCP with LiveKit](./streaming-mcp-livekit-ai-conversations.md)
- Both tasks involve HTTP streaming and web protocols
- Shared authentication infrastructure
- Could enable web-based AI-to-AI conversations

## Next Steps

1. Research claude.ai's external API capabilities
2. Prototype minimal HTTP wrapper
3. Test OAuth flow with mock provider
4. Experiment with browser audio APIs
5. Document findings and limitations