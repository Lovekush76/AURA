"""
Aura Assistant - Chat Streaming & Sovereign Profile Router
Serves Server-Sent Events (SSE) at /api/v1/chat/stream and profile persistence at /api/v1/chat/profile.
"""

import json
from fastapi import APIRouter, Depends
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
    session_id: str = Field("default_session", description="Conversation session ID for multi-turn isolation")

class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    linkedin_url: Optional[str] = None
    headline: Optional[str] = None
    skills: Optional[str] = None
    experience: Optional[str] = None
    education: Optional[str] = None
    location: Optional[str] = None

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
            location=req.location,
            session_id=req.session_id
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(sse_event_generator(), media_type="text/event-stream")

@router.get("/profile")
async def get_profile_endpoint(user: str = Depends(verify_auth_token)):
    container = get_container()
    profile = container.episodic_memory.get_profile()
    return {"ok": True, "profile": profile}

@router.post("/profile")
async def update_profile_endpoint(
    req: ProfileUpdateRequest,
    user: str = Depends(verify_auth_token)
):
    container = get_container()
    updates = {
        k: v.strip()
        for k, v in req.model_dump(exclude_none=True).items()
        if isinstance(v, str) and v.strip()
    }
    if updates:
        container.episodic_memory.update_profile_facts(updates, persist_sync=True)
    return {"ok": True, "profile": container.episodic_memory.get_profile()}

