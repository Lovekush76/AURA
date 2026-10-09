"""
Aura Assistant - Workspace API Router
Provides file management, AST diff application, Git rollback, and execution endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional

from aura_assistant.container import get_container
from aura_assistant.api.middleware.auth import verify_auth_token
from aura_assistant.core.workspace.patch_engine import PatchValidationError

router = APIRouter(prefix="/api/v1/workspace", tags=["workspace"])

class PatchRequest(BaseModel):
    diff: str = Field(..., description="Unified diff text")
    message: Optional[str] = Field(None, description="Optional commit message")

class RollbackRequest(BaseModel):
    commit_hash: str = Field(..., description="Target commit hash to restore")

class ExecuteRequest(BaseModel):
    language: str = Field("python", description="Target runtime: python or node")
    code: str = Field(..., description="Code to execute")
    network_profile: str = Field("none", description="Isolation profile: none, registry, open")
    timeout_s: int = Field(20, description="Execution timeout in seconds")

@router.get("/tree")
async def get_workspace_tree(user: str = Depends(verify_auth_token)):
    container = get_container()
    return {"ok": True, "files": container.workspace_service.get_file_tree()}

@router.get("/file")
async def read_file(path: str = Query(..., description="Relative file path"), user: str = Depends(verify_auth_token)):
    container = get_container()
    fs_tool = container.tools.get_tool("workspace_fs")
    result = await fs_tool.execute(action="read", path=path)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result

@router.post("/patch")
async def apply_patch_endpoint(req: PatchRequest, user: str = Depends(verify_auth_token)):
    container = get_container()
    try:
        result = container.workspace_service.apply_patch(req.diff, req.message)
        return {"ok": True, **result}
    except PatchValidationError as pve:
        raise HTTPException(status_code=422, detail=f"Patch Validation Failed: {str(pve)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to apply patch: {str(e)}")

@router.post("/rollback")
async def rollback_endpoint(req: RollbackRequest, user: str = Depends(verify_auth_token)):
    container = get_container()
    try:
        result = container.workspace_service.rollback(req.commit_hash)
        return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rollback failed: {str(e)}")

@router.get("/checkpoints")
async def list_checkpoints_endpoint(limit: int = 10, user: str = Depends(verify_auth_token)):
    container = get_container()
    return {"ok": True, "checkpoints": container.workspace_service.list_checkpoints(limit)}

@router.post("/execute")
async def execute_code_endpoint(req: ExecuteRequest, user: str = Depends(verify_auth_token)):
    container = get_container()
    code_tool = container.tools.get_tool("run_code")
    result = await code_tool.execute(
        language=req.language,
        code=req.code,
        network_profile=req.network_profile,
        timeout_s=req.timeout_s
    )
    return result
