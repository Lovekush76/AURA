"""
Aura Assistant - Git Checkpoint Engine & Rollback Manager
Creates atomic snapshots before and after patches, manages checkpoints,
and provides atomic rollback capabilities.
Supports real Git when available, and automatic file-snapshot fallback when Git is not installed.
"""

import os
import time
import shutil
import hashlib
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger("aura-checkpoints")

class CheckpointError(Exception):
    pass

class GitCheckpointManager:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
        self.fallback_dir = self.workspace_root / "data" / "checkpoints"
        self.fallback_dir.mkdir(parents=True, exist_ok=True)
        self.has_git = self._check_git_available()

        if self.has_git:
            self._ensure_git_initialized()

    def _check_git_available(self) -> bool:
        try:
            res = subprocess.run(["git", "--version"], capture_output=True)
            return res.returncode == 0
        except Exception:
            logger.info("Git binary not found in PATH. Operating in Snapshot-Checkpoint mode.")
            return False

    def _ensure_git_initialized(self):
        """Initializes a local git repository if one does not already exist."""
        git_dir = self.workspace_root / ".git"
        if not git_dir.exists():
            try:
                subprocess.run(["git", "init"], cwd=str(self.workspace_root), check=True, capture_output=True)
                subprocess.run(["git", "config", "user.name", "Aura Assistant"], cwd=str(self.workspace_root), check=True, capture_output=True)
                subprocess.run(["git", "config", "user.email", "aura@local.internal"], cwd=str(self.workspace_root), check=True, capture_output=True)
                logger.info(f"Initialized git tracking at {self.workspace_root}")
            except Exception as e:
                logger.warning(f"Git init skipped: {e}")
                self.has_git = False

    def create_checkpoint(self, message: str, author: str = "Aura Engine") -> Dict[str, Any]:
        """Stages all changes and commits a checkpoint snapshot."""
        if self.has_git:
            try:
                subprocess.run(["git", "add", "."], cwd=str(self.workspace_root), check=True, capture_output=True)
                status = subprocess.run(["git", "status", "--porcelain"], cwd=str(self.workspace_root), check=True, capture_output=True, text=True)
                if not status.stdout.strip():
                    head_rev = self.get_current_revision()
                    return {"checkpoint_id": head_rev, "committed": False, "message": "Working tree clean", "engine": "git"}

                commit_proc = subprocess.run(
                    ["git", "commit", "-m", f"[Aura Checkpoint] {message}", "--author", f"{author} <aura@local.internal>"],
                    cwd=str(self.workspace_root),
                    check=True,
                    capture_output=True,
                    text=True
                )
                commit_hash = self.get_current_revision()
                return {"checkpoint_id": commit_hash, "committed": True, "message": message, "engine": "git"}
            except Exception as e:
                logger.warning(f"Git commit failed ({e}). Falling back to snapshot checkpoint.")

        # Snapshot fallback
        now = int(time.time())
        snapshot_id = hashlib.sha256(f"{now}:{message}".encode()).hexdigest()[:10]
        snap_path = self.fallback_dir / f"snap_{now}_{snapshot_id}"
        snap_path.mkdir(parents=True, exist_ok=True)

        for item in self.workspace_root.iterdir():
            if item.name in [".git", "data", ".venv", "node_modules", "__pycache__"]:
                continue
            dest = snap_path / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)

        meta_file = snap_path / "_meta.txt"
        meta_file.write_text(f"{message}\n{author}\n{time.ctime()}", encoding="utf-8")

        return {
            "checkpoint_id": snapshot_id,
            "committed": True,
            "message": message,
            "engine": "snapshot"
        }

    def rollback(self, commit_hash: str) -> Dict[str, Any]:
        """Rolls back workspace state to a specific checkpoint."""
        if self.has_git:
            try:
                subprocess.run(["git", "reset", "--hard", commit_hash], cwd=str(self.workspace_root), check=True, capture_output=True)
                subprocess.run(["git", "clean", "-fd"], cwd=str(self.workspace_root), check=True, capture_output=True)
                return {"success": True, "restored_checkpoint": commit_hash, "engine": "git"}
            except Exception:
                pass

        # Look in snapshot directory
        for snap_dir in self.fallback_dir.glob(f"snap_*_{commit_hash}*"):
            for item in snap_dir.iterdir():
                if item.name == "_meta.txt":
                    continue
                dest = self.workspace_root / item.name
                if item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest)
            return {"success": True, "restored_checkpoint": commit_hash, "engine": "snapshot"}

        raise CheckpointError(f"Checkpoint {commit_hash} not found.")

    def get_current_revision(self) -> str:
        if self.has_git:
            try:
                res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(self.workspace_root), check=True, capture_output=True, text=True)
                return res.stdout.strip()
            except Exception:
                pass
        return "snap_head"

    def list_checkpoints(self, limit: int = 10) -> List[Dict[str, str]]:
        if self.has_git:
            try:
                res = subprocess.run(["git", "log", f"-n{limit}", "--pretty=format:%H|%an|%ad|%s"], cwd=str(self.workspace_root), check=True, capture_output=True, text=True)
                checkpoints = []
                for line in res.stdout.strip().splitlines():
                    if not line:
                        continue
                    parts = line.split("|")
                    if len(parts) >= 4:
                        checkpoints.append({"commit_hash": parts[0], "author": parts[1], "timestamp": parts[2], "message": parts[3]})
                if checkpoints:
                    return checkpoints
            except Exception:
                pass

        # Read snapshot fallbacks
        results = []
        for d in sorted(self.fallback_dir.glob("snap_*"), reverse=True)[:limit]:
            meta_p = d / "_meta.txt"
            msg = meta_p.read_text(encoding="utf-8").splitlines()[0] if meta_p.exists() else "Snapshot"
            results.append({
                "commit_hash": d.name.split("_")[-1],
                "author": "Aura Engine",
                "timestamp": time.ctime(d.stat().st_mtime),
                "message": msg
            })
        return results
