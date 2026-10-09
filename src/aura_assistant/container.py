"""
Aura Assistant - Dependency Injection Composition Root
Initializes all singletons, configurations, tools, and services.
"""

import yaml
from pathlib import Path

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
    def __init__(self, workspace_root: Path = None):
        self.workspace_root = workspace_root or Path(__file__).resolve().parent.parent.parent
        self.configs_dir = self.workspace_root / "configs"

        # Load configs
        tools_cfg = {}
        tools_path = self.configs_dir / "tools.yaml"
        if tools_path.exists():
            tools_cfg = yaml.safe_load(tools_path.read_text(encoding="utf-8")) or {}

        # Core Engines
        self.vram_arbiter = VRAMArbiter()
        self.llm_router = LLMRouter()
        self.ollama_provider = OllamaProvider()
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

_container_instance = None

def get_container(workspace_root: Path = None) -> Container:
    global _container_instance
    if _container_instance is None:
        _container_instance = Container(workspace_root)
    return _container_instance
