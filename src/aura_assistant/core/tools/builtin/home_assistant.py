"""
Aura Assistant - Home Assistant / IoT Controller Tool
"""

from typing import Dict, Any, Type
from pydantic import BaseModel, Field
from aura_assistant.core.tools.base import BaseTool

class HomeControlArgs(BaseModel):
    entity_id: str = Field(..., description="Entity identifier, e.g. 'light.office' or 'switch.desk'")
    action: str = Field("toggle", description="Action: 'turn_on', 'turn_off', 'toggle'")

class HomeAssistantTool(BaseTool):
    name = "home_control"
    description = "Control local smart home lights, switches, and sensors."
    sensitivity = "personal"
    requires_approval = False
    requires_voice_match = True

    @property
    def args_schema(self) -> Type[BaseModel]:
        return HomeControlArgs

    async def execute(self, entity_id: str = "", action: str = "toggle") -> Dict[str, Any]:
        critical_prefixes = ["lock.", "alarm_control_panel.", "cover.garage"]
        is_critical = any(entity_id.startswith(p) for p in critical_prefixes)
        
        # Local mock execution
        return {
            "ok": True,
            "entity_id": entity_id,
            "action": action,
            "state": "active",
            "is_critical": is_critical,
            "status": f"Successfully performed {action} on {entity_id}"
        }
