# Claude.ai Web + LiveKit iOS Audio Bridge

## Overview

Enable users to interact with Claude.ai through their web browser while speaking through the LiveKit iOS app, creating a seamless voice conversation experience with Claude using existing infrastructure.

## User Experience Vision

1. Open claude.ai in web browser (desktop/tablet)
2. Open LiveKit iOS app on phone
3. Join a LiveKit room from phone
4. Type or paste commands in claude.ai web
5. Claude's responses are spoken through LiveKit
6. User speaks responses through LiveKit iOS app
7. Transcribed text appears in claude.ai chat

## Architecture

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│  Claude.ai Web  │◄────────┤  Bridge Server   ├────────►│  LiveKit Cloud  │
│  (Text I/O)     │  Copy/  │  (Orchestrator)  │  Audio  │  or Self-Hosted │
└─────────────────┘  Paste  └──────────────────┘         └─────────────────┘
                                     │                              ▲
                                     │                              │
                                     ▼                              │
                            ┌──────────────────┐                    │
                            │  Voice-Mode MCP  │                    │
                            │  (Local/Cloud)   │                    │
                            └──────────────────┘                    │
                                                                    │
                                                          ┌─────────────────┐
                                                          │  LiveKit iOS    │
                                                          │  (Audio I/O)    │
                                                          └─────────────────┘
```

## Implementation Approaches

### Option 1: Browser Extension Bridge (Simplest)

A browser extension that bridges claude.ai with LiveKit:

**Components:**
1. **Browser Extension**
   - Injects controls into claude.ai interface
   - Monitors chat messages
   - Connects to bridge server
   - Auto-copies transcribed text to chat

2. **Bridge Server**
   - Manages LiveKit room
   - Runs voice-mode for TTS/STT
   - Coordinates between web and mobile
   - Handles state synchronization

3. **LiveKit iOS App**
   - Standard LiveKit app
   - Joins room with room code
   - Handles audio I/O only

**User Flow:**
```
1. Install browser extension
2. Extension shows "Connect Voice" button on claude.ai
3. Click button → get room code
4. Enter room code in LiveKit iOS app
5. Start talking, text appears in claude.ai
6. Claude's responses are spoken through iOS
```

### Option 2: Copy/Paste Orchestrator (No Extension)

A standalone orchestrator that uses copy/paste:

**Workflow:**
1. Run orchestrator (locally or cloud)
2. Orchestrator creates LiveKit room
3. Join room from iOS app
4. Orchestrator shows web UI with transcript
5. Copy text from orchestrator to claude.ai
6. Copy Claude's response back to orchestrator
7. Orchestrator speaks response through LiveKit

**Benefits:**
- No browser extension needed
- Works with any AI chat interface
- Full control over orchestration

### Option 3: MCP-Powered Integration

If claude.ai gains MCP client capabilities:

**Architecture:**
1. Voice-mode exposes streaming MCP endpoint
2. Configure claude.ai project to use MCP endpoint
3. LiveKit integration built into voice-mode
4. Direct connection, no bridge needed

## Technical Implementation

### Browser Extension (Option 1)

```javascript
// Content script for claude.ai
const bridgeClient = new BridgeClient();

// Add voice button to interface
const voiceButton = createVoiceButton();
document.querySelector('.chat-input').appendChild(voiceButton);

// Monitor for new messages
const observer = new MutationObserver((mutations) => {
  mutations.forEach((mutation) => {
    if (isClaudeResponse(mutation)) {
      bridgeClient.sendToTTS(extractText(mutation));
    }
  });
});

// Handle transcribed text
bridgeClient.on('transcription', (text) => {
  insertTextToChat(text);
  triggerSend();
});
```

### Bridge Server

```python
from fastapi import FastAPI, WebSocket
from livekit import api, rtc
import voice_mode

app = FastAPI()

class ConversationBridge:
    def __init__(self):
        self.livekit_room = None
        self.websocket_clients = []
        self.voice_mode = VoiceModeClient()
    
    async def create_room(self) -> str:
        """Create LiveKit room and return join code"""
        room_name = generate_room_name()
        await create_livekit_room(room_name)
        return self.generate_join_url(room_name)
    
    async def on_audio_received(self, audio_data):
        """Handle audio from iOS app"""
        # STT processing
        text = await self.voice_mode.speech_to_text(audio_data)
        
        # Send to all web clients
        await self.broadcast_to_web({
            "type": "transcription",
            "text": text
        })
    
    async def on_text_received(self, text: str):
        """Handle text from web (Claude's response)"""
        # TTS processing
        audio = await self.voice_mode.text_to_speech(text)
        
        # Send to LiveKit room
        await self.publish_audio_to_room(audio)

@app.websocket("/bridge")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    bridge.websocket_clients.append(websocket)
    # Handle bidirectional communication
```

### Orchestrator UI (Option 2)

Simple web interface for copy/paste workflow:

```html
<!DOCTYPE html>
<html>
<head>
    <title>Voice Bridge Orchestrator</title>
</head>
<body>
    <div id="status">
        <h2>LiveKit Room: <span id="room-code"></span></h2>
        <p>Status: <span id="connection-status">Waiting for iOS app...</span></p>
    </div>
    
    <div id="transcription">
        <h3>You said:</h3>
        <div id="user-text" class="copy-box"></div>
        <button onclick="copyToClipboard('user-text')">Copy to Claude</button>
    </div>
    
    <div id="response">
        <h3>Paste Claude's response:</h3>
        <textarea id="claude-response"></textarea>
        <button onclick="speakResponse()">Speak Response</button>
    </div>
    
    <div id="history">
        <h3>Conversation History</h3>
        <div id="chat-history"></div>
    </div>
</body>
</html>
```

## LiveKit iOS App Configuration

### Standard LiveKit App
- Use existing LiveKit iOS sample app
- Configure with room URL and token
- Minimal modifications needed

### Custom Features (Optional)
- Push-to-talk button
- Voice activity indicator
- Mute/unmute controls
- Connection status

## Security Considerations

1. **Authentication**
   - Time-limited room tokens
   - Optional PIN codes
   - No permanent storage of audio

2. **Privacy**
   - End-to-end encryption option
   - Local-only mode available
   - No cloud dependency (self-host)

3. **Access Control**
   - Room auto-expires after inactivity
   - Single user per room by default
   - Rate limiting on bridge server

## Deployment Options

### Local Development
```bash
# Run bridge server locally
python bridge_server.py --port 8080

# Connect browser extension to localhost
# Use ngrok for iOS testing
ngrok http 8080
```

### Cloud Deployment
```yaml
# docker-compose.yml
version: '3'
services:
  bridge:
    image: voice-bridge:latest
    environment:
      - LIVEKIT_URL=${LIVEKIT_URL}
      - LIVEKIT_API_KEY=${LIVEKIT_API_KEY}
    ports:
      - "443:8080"
```

### Hybrid Mode
- Bridge server in cloud
- Voice-mode running locally
- Best of both worlds

## Progressive Enhancement Path

1. **Phase 1: Copy/Paste MVP**
   - Basic orchestrator UI
   - Manual copy/paste
   - Proof of concept

2. **Phase 2: Browser Extension**
   - Auto-inject into claude.ai
   - Seamless experience
   - Firefox/Chrome support

3. **Phase 3: Native Integration**
   - If/when claude.ai supports external connections
   - Direct MCP integration
   - No bridge needed

## Alternative Approaches

### Using Shortcuts/Automation
- iOS Shortcuts to streamline flow
- Keyboard Maestro for desktop automation
- IFTTT/Zapier integration

### Voice-Only Interface
- Skip claude.ai entirely
- Pure voice conversation
- Bridge translates to Claude API

### Multi-Modal Sync
- Screen sharing from iOS
- See claude.ai on phone
- Voice + visual synchronization

## Benefits of This Approach

1. **No Claude.ai Modifications**
   - Works with existing interface
   - No API access needed
   - Future-proof

2. **Leverages LiveKit**
   - Proven infrastructure
   - Low latency audio
   - Multi-platform support

3. **Flexible Architecture**
   - Can work with any chat interface
   - Not limited to Claude
   - Extensible design

## Challenges & Solutions

### Challenge: Copy/Paste Friction
**Solution:** Browser extension for automation

### Challenge: iOS Audio Permissions  
**Solution:** Use established LiveKit app

### Challenge: Synchronization
**Solution:** Real-time state management in bridge

### Challenge: Network Latency
**Solution:** Local bridge option, edge deployment

## Next Steps

1. **Validate Approach**
   - Test LiveKit iOS app capabilities
   - Verify browser extension feasibility
   - Check claude.ai DOM structure

2. **Build MVP**
   - Simple bridge server
   - Basic orchestrator UI
   - Test with LiveKit iOS

3. **Iterate Based on Usage**
   - Add automation features
   - Improve UX
   - Optimize performance

## Related Tasks

- [Streaming MCP with LiveKit](./streaming-mcp-livekit-ai-conversations.md)
- [Voice-Mode Streaming HTTP & OAuth](./voice-mode-streaming-oauth-web.md)

This approach provides an immediate solution while building toward future direct integration possibilities.