"""
Aura Assistant - Voice IPC WebSocket Router
Handles bi-directional communication with the host-native Voice Daemon.
"""

import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from aura_assistant.container import get_container

logger = logging.getLogger("aura-voice-ipc-router")

router = APIRouter(prefix="/api/v1/voice", tags=["voice"])

@router.get("/status")
async def voice_status():
    return {
        "status": "online",
        "channels": ["websocket_ipc", "browser_web_speech"],
        "ipc_endpoint": "/api/v1/voice/ipc"
    }

@router.websocket("/ipc")
async def voice_ipc_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("Voice Daemon IPC connection established.")
    container = get_container()
    chat_service = container.chat_service

    try:
        while True:
            raw_text = await websocket.receive_text()
            payload = json.loads(raw_text)
            event_type = payload.get("event")

            if event_type == "telemetry":
                state = payload.get("state")
                logger.debug(f"Voice Daemon Telemetry: {state}")

            elif event_type == "utterance":
                user_text = payload.get("text", "")
                confidence = payload.get("confidence", 1.0)
                speaker_verified = payload.get("speaker_verified", True)
                biometric_score = payload.get("biometric_score", 1.0)

                logger.info(f"Received Utterance from Voice Daemon: '{user_text}' (verified={speaker_verified})")

                # Stream response from chat service
                async for chunk in chat_service.handle_message_stream(
                    prompt=user_text,
                    channel="voice",
                    speaker_verified=speaker_verified,
                    biometric_score=biometric_score
                ):
                    if chunk.get("type") == "voice_sentences":
                        for sentence in chunk.get("sentences", []):
                            await websocket.send_text(json.dumps({
                                "event": "tts_chunk",
                                "sentence": sentence
                            }))

                await websocket.send_text(json.dumps({"event": "tts_end"}))

    except WebSocketDisconnect:
        logger.info("Voice Daemon IPC disconnected.")
    except Exception as e:
        logger.error(f"Error in Voice IPC socket: {e}")
        try:
            await websocket.close()
        except Exception:
            pass
