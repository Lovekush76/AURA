"""
Aura Assistant - Workspace Synchronization Service
Coordinates AST patch validation, Git checkpoints, and filesystem state.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional

from aura_assistant.core.workspace.patch_engine import PatchEngine, PatchValidationError
from aura_assistant.core.workspace.checkpoints import GitCheckpointManager, CheckpointError
from aura_assistant.core.workspace.indexer import WorkspaceIndexer

class WorkspaceService:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
        self.patch_engine = PatchEngine(self.workspace_root)
        self.checkpoint_manager = GitCheckpointManager(self.workspace_root)
        self.indexer = WorkspaceIndexer(self.workspace_root)

    def apply_patch(self, diff_text: str, commit_message: Optional[str] = None) -> Dict[str, Any]:
        """Validates patch AST, applies diff, and automatically creates a git checkpoint."""
        # 1. Apply patch with AST syntax verification
        result = self.patch_engine.validate_and_apply(diff_text)

        # 2. Commit git checkpoint
        msg = commit_message or f"Applied patch modifying {len(result['modified_files'])} files"
        checkpoint_info = self.checkpoint_manager.create_checkpoint(msg)

        return {
            **result,
            "checkpoint": checkpoint_info
        }

    def rollback(self, commit_hash: str) -> Dict[str, Any]:
        return self.checkpoint_manager.rollback(commit_hash)

    def list_checkpoints(self, limit: int = 10) -> List[Dict[str, str]]:
        return self.checkpoint_manager.list_checkpoints(limit=limit)

    def get_file_tree(self) -> List[Dict[str, Any]]:
        tree = []
        for p in self.workspace_root.rglob("*"):
            if any(part.startswith(".") for part in p.parts):
                continue
            rel = str(p.relative_to(self.workspace_root))
            tree.append({
                "path": rel,
                "is_dir": p.is_dir(),
                "size": p.stat().st_size if not p.is_dir() else 0
            })
        return tree
