"""
Aura Assistant - Voice Daemon IPC Client
Manages authenticated WebSocket streaming to the FastAPI Core API.
"""

import json
import logging
import asyncio
from typing import Dict, Any, Callable, Optional, Awaitable
import websockets

logger = logging.getLogger("aura-voice-ipc-client")

class VoiceIPCClient:
    def __init__(self, ws_url: str = "ws://127.0.0.1:8000/api/v1/voice/ipc"):
        self.ws_url = ws_url
        self.ws: Optional[websockets.WebSocketClientProtocol] = None

    async def connect(self) -> websockets.WebSocketClientProtocol:
        logger.info(f"Connecting to Aura Core API IPC at {self.ws_url}...")
        self.ws = await websockets.connect(self.ws_url)
        logger.info("Connected to Aura Core API.")
        return self.ws

    async def send_event(self, event_type: str, data: Dict[str, Any]):
        if not self.ws or self.ws.closed:
            raise ConnectionError("Voice IPC client not connected.")
        payload = {"event": event_type, **data}
        await self.ws.send(json.dumps(payload))

    async def send_utterance(self, text: str, confidence: float, speaker_verified: bool, biometric_score: float = 1.0):
        await self.send_event("utterance", {
            "text": text,
            "confidence": confidence,
            "speaker_verified": speaker_verified,
            "biometric_score": biometric_score,
            "channel": "voice"
        })

    async def send_telemetry(self, state: str):
        await self.send_event("telemetry", {"state": state})

    async def close(self):
        if self.ws and not self.ws.closed:
            await self.ws.close()
