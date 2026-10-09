#!/usr/bin/env python3
"""
Aura Assistant - One-Click Local Orchestrator
Boots the entire Aura system locally:
1. Sandbox Broker (Local Isolation + Docker detection)
2. FastAPI Core Engine (127.0.0.1:8000)
3. Voice Daemon IPC client
"""

import sys
import os
import time
import subprocess
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
PYTHON_EXE = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe" if sys.platform == "win32" else PROJECT_ROOT / ".venv" / "bin" / "python"

if not PYTHON_EXE.exists():
    PYTHON_EXE = Path(sys.executable)

def get_env():
    env = os.environ.copy()
    src_path = str(PROJECT_ROOT / "src")
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = f"{src_path}{os.pathsep}{str(PROJECT_ROOT)}{os.pathsep}{env['PYTHONPATH']}"
    else:
        env["PYTHONPATH"] = f"{src_path}{os.pathsep}{str(PROJECT_ROOT)}"
    return env

def run_broker():
    print("[Aura] Launching Sandbox Broker daemon...")
    broker_script = PROJECT_ROOT / "daemons" / "sandbox" / "broker.py"
    subprocess.run([str(PYTHON_EXE), str(broker_script)], cwd=str(PROJECT_ROOT), env=get_env())

def run_api():
    print("[Aura] Launching FastAPI Core on http://127.0.0.1:8000 ...")
    cmd = [
        str(PYTHON_EXE), "-m", "uvicorn",
        "aura_assistant.api.app:app",
        "--host", "127.0.0.1",
        "--port", "8000",
        "--workers", "1"
    ]
    subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=get_env())

def main():
    print("=" * 60)
    print(">>> AURA ASSISTANT v3.5 - LOCAL SYSTEM LAUNCHER <<<")
    print("=" * 60)
    print(f"Project Root: {PROJECT_ROOT}")
    print(f"Python Runtime: {PYTHON_EXE}")

    # Start Sandbox Broker in background thread
    broker_thread = threading.Thread(target=run_broker, daemon=True)
    broker_thread.start()
    time.sleep(1.0)

    # Start FastAPI Core (blocking main thread)
    try:
        run_api()
    except KeyboardInterrupt:
        print("\n[Aura] Shutting down local services gracefully.")

if __name__ == "__main__":
    main()
