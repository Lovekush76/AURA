"""
Aura Assistant - Code Execution Tool
Dispatches ephemeral code execution requests to the privileged Host Sandbox Broker via IPC.
"""

import json
import logging
import uuid
from typing import Dict, Any, Type
from pydantic import BaseModel, Field

from aura_assistant.core.tools.base import BaseTool
from aura_assistant.core.ipc import connect_ipc_client, get_socket_path

logger = logging.getLogger("aura-tool-code-exec")

class CodeExecArgs(BaseModel):
    language: str = Field("python", description="Language runtime: 'python' or 'node'")
    code: str = Field(..., description="Source code to execute inside the isolated sandbox")
    network_profile: str = Field("none", description="Network isolation profile: 'none', 'registry', or 'open'")
    timeout_s: int = Field(20, description="Execution timeout in seconds")

class CodeExecutionTool(BaseTool):
    name = "run_code"
    description = "Executes arbitrary code safely inside an ephemeral cgroup-isolated sandbox."
    sensitivity = "personal"
    requires_approval = False
    requires_voice_match = True
    timeout_s = 25

    def __init__(self, socket_path: str = None):
        self.socket_path = socket_path or get_socket_path("SANDBOX_SOCKET_PATH", "/run/aura/sandbox.sock")

    @property
    def args_schema(self) -> Type[BaseModel]:
        return CodeExecArgs

    async def execute(self, language: str = "python", code: str = "", network_profile: str = "none", timeout_s: int = 20) -> Dict[str, Any]:
        payload = {
            "run_id": f"exec-{uuid.uuid4().hex[:8]}",
            "language": language,
            "code": code,
            "network_profile": network_profile,
            "timeout_s": timeout_s
        }

        try:
            reader, writer = await connect_ipc_client(self.socket_path)
            writer.write(json.dumps(payload).encode() + b"\n")
            await writer.drain()

            raw_resp = await reader.readuntil(b"\n")
            writer.close()
            await writer.wait_closed()

            return json.loads(raw_resp.decode().strip())
        except Exception as e:
            logger.error(f"Failed to communicate with Sandbox Broker: {e}")
            return {
                "ok": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Sandbox broker unavailable: {str(e)}",
                "error": "Broker IPC failure"
            }
