"""
Aura Assistant - Chat Streaming Router
Serves Server-Sent Events (SSE) at /api/v1/chat/stream.
"""

import json
from fastapi import APIRouter, Depends, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

from aura_assistant.container import get_container
from aura_assistant.api.middleware.auth import verify_auth_token

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

class ChatStreamRequest(BaseModel):
    prompt: str = Field(..., description="User prompt or task instruction")
    channel: str = Field("text", description="Input channel: 'text' or 'voice'")
    speaker_verified: bool = Field(True, description="Speaker verified indicator")
    biometric_score: float = Field(1.0, description="Biometric verification score")
    override_model: Optional[str] = Field(None, description="Explicit model override")
    location: Optional[Dict[str, Any]] = Field(None, description="Client real-time location payload")

@router.post("/stream")
async def stream_chat_endpoint(
    req: ChatStreamRequest,
    user: str = Depends(verify_auth_token)
):
    container = get_container()
    chat_service = container.chat_service

    async def sse_event_generator():
        async for event in chat_service.handle_message_stream(
            prompt=req.prompt,
            channel=req.channel,
            speaker_verified=req.speaker_verified,
            biometric_score=req.biometric_score,
            override_model=req.override_model,
            location=req.location
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(sse_event_generator(), media_type="text/event-stream")
