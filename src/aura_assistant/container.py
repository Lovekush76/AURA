"""
Aura Assistant - Dependency Injection Composition Root
Initializes all singletons, shared HTTP client pool, configurations, tools, and services.
"""

import yaml
import httpx
from pathlib import Path
from typing import Optional

from aura_assistant.core.llm.provider import OllamaProvider
from aura_assistant.core.llm.router import LLMRouter
from aura_assistant.core.llm.residency import VRAMArbiter
from aura_assistant.core.voice.gating import BiometricGating
from aura_assistant.core.memory.episodic import EpisodicMemoryManager
from aura_assistant.core.tools.registry import ToolRegistry
from aura_assistant.core.tools.builtin.code_exec import CodeExecutionTool
from aura_assistant.core.tools.builtin.filesystem import FilesystemTool
from aura_assistant.core.tools.builtin.home_assistant import HomeAssistantTool
from aura_assistant.core.context import ContextEngine
from aura_assistant.services.workspace_service import WorkspaceService
from aura_assistant.services.chat_service import ChatService


class Container:
    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = workspace_root or Path(__file__).resolve().parent.parent.parent
        self.configs_dir = self.workspace_root / "configs"

        # Load configs
        tools_cfg = {}
        tools_path = self.configs_dir / "tools.yaml"
        if tools_path.exists():
            tools_cfg = yaml.safe_load(tools_path.read_text(encoding="utf-8")) or {}

        # Shared process-wide HTTP client for connection pooling across router, provider, and NIM
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=2.5, read=120.0, write=10.0, pool=5.0),
            limits=httpx.Limits(max_keepalive_connections=25, max_connections=60)
        )

        # Core Engines
        self.vram_arbiter = VRAMArbiter()
        self.llm_router = LLMRouter(
            vram_arbiter=self.vram_arbiter,
            http_client=self.http_client
        )
        self.ollama_provider = OllamaProvider(
            http_client=self.http_client,
            on_model_missing=self.llm_router.invalidate_model_cache
        )
        self.biometric_gating = BiometricGating(tools_cfg)
        self.episodic_memory = EpisodicMemoryManager(self.workspace_root / "data" / "memory")
        self.context_engine = ContextEngine()

        # Tools Registry
        self.tools = ToolRegistry(self.biometric_gating)
        self.tools.register(CodeExecutionTool())
        self.tools.register(FilesystemTool(self.workspace_root))
        self.tools.register(HomeAssistantTool())

        # Domain Services
        self.workspace_service = WorkspaceService(self.workspace_root)
        self.chat_service = ChatService(
            router=self.llm_router,
            provider=self.ollama_provider,
            tools=self.tools,
            memory=self.episodic_memory,
            context_engine=self.context_engine
        )

    async def aclose(self) -> None:
        """Flushes background tasks and closes the shared HTTP client pool cleanly."""
        if hasattr(self.chat_service, "shutdown"):
            await self.chat_service.shutdown()
        if self.http_client and not self.http_client.is_closed:
            await self.http_client.aclose()


_container_instance: Optional[Container] = None


def get_container(workspace_root: Optional[Path] = None) -> Container:
    global _container_instance
    if _container_instance is None:
        _container_instance = Container(workspace_root)
    return _container_instance
