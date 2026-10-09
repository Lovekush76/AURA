"""
Aura Assistant - FastAPI Application Core
Lifecycle management, CORS configuration, router registrations, and health check.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aura_assistant.container import get_container
from aura_assistant.api.routers import chat, voice_ipc, workspace

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("aura-app-core")

from aura_assistant.core.db.session import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Aura Core Engine & SQLite Database Schema...")
    try:
        init_db()
    except Exception as e:
        logger.warning(f"Database initialization warning: {e}")
    container = get_container()
    # Attempt to pre-warm pinned models
    try:
        await container.llm_router.warm_pinned_models()
    except Exception as e:
        logger.warning(f"Model pre-warm warning (Ollama might be offline): {e}")
    logger.info("Aura Core is ready.")
    yield
    logger.info("Shutting down Aura Core Engine...")

app = FastAPI(
    title="Aura Assistant Core API",
    version="3.5.0",
    description="Sovereign AI Assistant with Acoustic Core, Multi-Model Routing, and Sandboxed Workspace",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers
app.include_router(chat.router)
app.include_router(voice_ipc.router)
app.include_router(workspace.router)

@app.get("/health")
async def health_check():
    container = get_container()
    ollama_ok = await container.ollama_provider.check_health()
    vram_status = container.vram_arbiter.get_telemetry()
    return {
        "status": "online",
        "version": "3.5.0",
        "ollama_online": ollama_ok,
        "vram_status": vram_status
    }
