"""
Aura Assistant - Jailed Filesystem Tool
Executes workspace filesystem queries within strict sandbox directory boundaries.
"""

import os
from pathlib import Path
from typing import Dict, Any, Type, List
from pydantic import BaseModel, Field

from aura_assistant.core.tools.base import BaseTool

class FilesystemArgs(BaseModel):
    action: str = Field(..., description="Action: 'read', 'list', or 'stat'")
    path: str = Field(..., description="Relative workspace path")

class FilesystemTool(BaseTool):
    name = "workspace_fs"
    description = "Inspect files and directory trees within the jailed workspace."
    sensitivity = "personal"
    requires_approval = False
    requires_voice_match = True

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()

    @property
    def args_schema(self) -> Type[BaseModel]:
        return FilesystemArgs

    def _resolve_safe_path(self, relative_path: str) -> Path:
        resolved = (self.workspace_root / relative_path).resolve()
        if not resolved.is_relative_to(self.workspace_root):
            raise PermissionError("Path traversal violation")
        if resolved.name in [".env", "id_rsa"] or ".git" in resolved.parts:
            raise PermissionError("Access to protected file prohibited")
        return resolved

    async def execute(self, action: str = "read", path: str = ".") -> Dict[str, Any]:
        try:
            safe_p = self._resolve_safe_path(path)
            if action == "read":
                if not safe_p.exists() or safe_p.is_dir():
                    return {"ok": False, "error": f"File does not exist: {path}"}
                return {"ok": True, "content": safe_p.read_text(encoding="utf-8")}
            elif action == "list":
                if not safe_p.exists():
                    return {"ok": False, "error": f"Path not found: {path}"}
                items = [p.name for p in safe_p.iterdir() if not p.name.startswith(".git")]
                return {"ok": True, "items": items}
            elif action == "stat":
                stat = safe_p.stat()
                return {"ok": True, "size": stat.st_size, "is_dir": safe_p.is_dir()}
            return {"ok": False, "error": f"Unknown action: {action}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
