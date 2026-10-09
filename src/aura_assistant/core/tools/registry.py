"""
Aura Assistant - Dynamic Tool Registry & Execution Dispatcher
Enforces role-based permissions, biometric sensitivity gating, and execution timeouts.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from aura_assistant.core.tools.base import BaseTool
from aura_assistant.core.voice.gating import BiometricGating

logger = logging.getLogger("aura-tool-registry")

class ToolRegistry:
    def __init__(self, gating: Optional[BiometricGating] = None):
        self._tools: Dict[str, BaseTool] = {}
        self.gating = gating

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name} (sensitivity: {tool.sensitivity})")

    def get_tool(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_available_tools(
        self,
        speaker_verified: bool = True,
        biometric_score: float = 1.0,
        channel: str = "text"
    ) -> List[Dict[str, Any]]:
        tool_names = list(self._tools.keys())
        if self.gating:
            tool_names = self.gating.filter_allowed_tools(
                available_tool_names=tool_names,
                speaker_verified=speaker_verified,
                biometric_score=biometric_score,
                channel=channel
            )

        result = []
        for name in tool_names:
            t = self._tools[name]
            result.append({
                "name": t.name,
                "description": t.description,
                "sensitivity": t.sensitivity,
                "requires_approval": t.requires_approval
            })
        return result

    async def execute_tool(
        self,
        name: str,
        params: Dict[str, Any],
        speaker_verified: bool = True,
        biometric_score: float = 1.0,
        channel: str = "text"
    ) -> Dict[str, Any]:
        tool = self.get_tool(name)
        if not tool:
            return {"ok": False, "error": f"Tool '{name}' not found in registry."}

        # Check biometric clearance
        if channel == "voice" and tool.requires_voice_match:
            if not speaker_verified or biometric_score < 0.85:
                return {
                    "ok": False,
                    "error": f"Permission Denied: Biometric speaker verification required for tool '{name}'."
                }

        try:
            # Validate parameters with args_schema
            validated_args = tool.args_schema(**params).model_dump()
            return await asyncio.wait_for(tool.execute(**validated_args), timeout=tool.timeout_s)
        except asyncio.TimeoutError:
            return {"ok": False, "error": f"Tool execution timed out after {tool.timeout_s}s"}
        except Exception as e:
            logger.error(f"Error executing tool '{name}': {e}")
            return {"ok": False, "error": str(e)}
