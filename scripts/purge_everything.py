#!/usr/bin/env python3
"""
Aura Assistant - Zero-Residue Project Purge Script
Invoked when user requests "delete everything". Completely removes all project artifacts,
dependencies, virtual environments, caches, logs, databases, and temporary run files.
"""

import sys
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

TARGETS_TO_REMOVE = [
    # Virtualenvs & dependencies
    PROJECT_ROOT / ".venv",
    PROJECT_ROOT / "venv",
    PROJECT_ROOT / "frontend" / "node_modules",
    PROJECT_ROOT / "frontend" / "dist",
    
    # Runtime sockets & data
    PROJECT_ROOT / "run",
    PROJECT_ROOT / "data",
    PROJECT_ROOT / "logs",
    Path("/tmp/aura-runs"),
    Path("/run/aura"),
    
    # Python cache directories
    PROJECT_ROOT / ".pytest_cache",
    PROJECT_ROOT / ".ruff_cache",
    PROJECT_ROOT / ".mypy_cache",
]

def purge_project(keep_spec: bool = False):
    print("=" * 60)
    print(">>> AURA ZERO-RESIDUE PURGE ENGINE INITIALIZED <<<")
    print(f"Target Root: {PROJECT_ROOT}")
    print("=" * 60)

    # 1. Kill any running project processes if active
    print("[1/4] Terminating running Aura background processes...")
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/FI", "WINDOWTITLE eq *aura*"], capture_output=True)
        else:
            subprocess.run(["pkill", "-f", "aura_assistant"], capture_output=True)
            subprocess.run(["pkill", "-f", "aura-voice-daemon"], capture_output=True)
            subprocess.run(["pkill", "-f", "aura-sandbox-broker"], capture_output=True)
    except Exception as e:
        print(f"  Notice: Process cleanup skipped or completed: {e}")

    # 2. Stop and remove Docker containers if docker is running
    print("[2/4] Checking and removing Docker containers...")
    try:
        subprocess.run(["docker", "rm", "-f", "aura-sandbox-python", "aura-sandbox-node"], capture_output=True)
    except Exception:
        pass

    # 3. Clean specific caches and directories
    print("[3/4] Purging caches, node_modules, logs, and run directories...")
    for target in TARGETS_TO_REMOVE:
        if target.exists():
            print(f"  Removing: {target}")
            try:
                if target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
                else:
                    target.unlink(missing_ok=True)
            except Exception as e:
                print(f"  Warning: Failed to delete {target}: {e}")

    # Clean __pycache__ recursively
    for pycache in PROJECT_ROOT.rglob("__pycache__"):
        try:
            shutil.rmtree(pycache, ignore_errors=True)
        except Exception:
            pass

    for pyc in PROJECT_ROOT.rglob("*.pyc"):
        try:
            pyc.unlink(missing_ok=True)
        except Exception:
            pass

    # 4. Optional full deletion of the codebase itself
    if not keep_spec:
        print("[4/4] Purging entire codebase directory...")
        try:
            # Note: We delete all content inside PROJECT_ROOT
            for item in PROJECT_ROOT.iterdir():
                try:
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                    else:
                        item.unlink(missing_ok=True)
                except Exception as ex:
                    print(f"  Warning deleting {item}: {ex}")
            print("  Entire Aura workspace wiped completely.")
        except Exception as e:
            print(f"  Failed full workspace purge: {e}")
    else:
        print("[4/4] Preserved source specifications while purging all caches and dependencies.")

    print("=" * 60)
    print(">>> ZERO-RESIDUE PURGE COMPLETE. SYSTEM RESTORED. <<<")
    print("=" * 60)

if __name__ == "__main__":
    purge_project(keep_spec=False)
