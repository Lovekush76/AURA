"""
Aura Assistant - Voice IPC WebSocket Router
Handles bi-directional communication with the host-native Voice Daemon
with loopback/token verification and biometric score clamping.
"""

import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from aura_assistant.container import get_container
from aura_assistant.api.middleware.auth import is_valid_token

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
    # Verify loopback client or valid bearer/query token
    client_host = websocket.client.host if websocket.client else ""
    auth_header = websocket.headers.get("authorization", "")
    bearer_token = auth_header.replace("Bearer ", "").strip() if auth_header.startswith("Bearer ") else ""
    query_token = websocket.query_params.get("token", "")
    token = bearer_token or query_token

    is_loopback = client_host in ("127.0.0.1", "::1", "localhost", "testclient")
    if not is_loopback and not is_valid_token(token):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

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
                user_text = str(payload.get("text", "")).strip()
                if not user_text:
                    continue
                speaker_verified = bool(payload.get("speaker_verified", False))
                raw_score = float(payload.get("biometric_score", 0.0))
                biometric_score = max(0.0, min(1.0, raw_score))
                session_id = str(payload.get("session_id", "voice_daemon_session"))


                logger.info(f"Received Utterance from Voice Daemon: '{user_text}' (verified={speaker_verified}, score={biometric_score:.2f})")

                async for chunk in chat_service.handle_message_stream(
                    prompt=user_text,
                    channel="voice",
                    speaker_verified=speaker_verified,
                    biometric_score=biometric_score,
                    session_id=session_id
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
