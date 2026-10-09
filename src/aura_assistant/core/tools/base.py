"""
Aura Assistant - Base Tool Interface & Metadata Schema
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Type
from pydantic import BaseModel, Field

class BaseTool(ABC):
    name: str
    description: str
    sensitivity: str = "personal"  # "public", "personal", "critical"
    requires_approval: bool = False
    requires_voice_match: bool = True
    timeout_s: int = 15

    @property
    @abstractmethod
    def args_schema(self) -> Type[BaseModel]:
        """Returns the Pydantic schema for the tool inputs."""
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Asynchronously executes the tool action."""
        pass
