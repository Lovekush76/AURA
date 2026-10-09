#!/usr/bin/env python3
"""
Aura Assistant - Privileged Host Sandbox Broker
Listens on local IPC (Unix Domain Socket or Local Loopback) and executes code
either inside strictly isolated Docker containers (with cgroup v2 enforcement)
or in a local isolated subprocess sandbox if Docker daemon is not active.
"""

import sys
import os
import asyncio
import json
import logging
import shutil
import uuid
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional

try:
    import docker
    from docker.errors import DockerException
    HAS_DOCKER = True
except ImportError:
    HAS_DOCKER = False

# Add repo root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
from aura_assistant.core.ipc import create_ipc_server, get_socket_path
from daemons.sandbox.cgroups import CgroupConstraints

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("aura-sandbox-broker")

SOCKET_PATH = get_socket_path("SANDBOX_SOCKET_PATH", "/run/aura/sandbox.sock")
BASE_RUN_DIR = Path(tempfile.gettempdir()) / "aura-runs"

@dataclass
class ExecutionRequest:
    run_id: str
    language: str
    code: str
    network_profile: str
    timeout_s: int

class SandboxBroker:
    def __init__(self):
        BASE_RUN_DIR.mkdir(parents=True, exist_ok=True)
        self.docker_client = None
        self.constraints = CgroupConstraints()
        
        if HAS_DOCKER:
            try:
                self.docker_client = docker.from_env()
                # Test connectivity
                self.docker_client.ping()
                logger.info("Docker daemon verified. Using containerized cgroup sandbox.")
            except Exception as e:
                logger.warning(f"Docker unreachable ({e}). Operating in Local Process Isolation mode.")
                self.docker_client = None
        else:
            logger.warning("Docker package not found. Operating in Local Process Isolation mode.")

        self.image_map = {
            "python": "aura-sandbox-python:latest",
            "node": "aura-sandbox-node:latest"
        }

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            raw_data = await reader.readuntil(b"\n")
            payload = json.loads(raw_data.decode().strip())
            
            req = ExecutionRequest(
                run_id=payload.get("run_id", str(uuid.uuid4())),
                language=payload.get("language", "python"),
                code=payload.get("code", ""),
                network_profile=payload.get("network_profile", "none"),
                timeout_s=int(payload.get("timeout_s", 20))
            )

            result = await self._execute(req)
            writer.write(json.dumps(result).encode() + b"\n")
            await writer.drain()
        except Exception as e:
            logger.error(f"Error handling broker request: {e}")
            err_resp = {"ok": False, "error": str(e), "stdout": "", "stderr": ""}
            writer.write(json.dumps(err_resp).encode() + b"\n")
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def _execute(self, req: ExecutionRequest) -> Dict[str, Any]:
        if self.docker_client:
            return await self._execute_docker(req)
        return await self._execute_local_isolated(req)

    async def _execute_docker(self, req: ExecutionRequest) -> Dict[str, Any]:
        run_dir = BASE_RUN_DIR / req.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        
        file_name = "main.py" if req.language == "python" else "index.js"
        source_path = run_dir / file_name
        source_path.write_text(req.code, encoding="utf-8")

        # Network topology mapping
        network_mode = "none"
        environment = {}
        if req.network_profile == "registry":
            network_mode = "aura-egress"
            environment = {
                "HTTP_PROXY": "http://aura-egress-proxy:3128",
                "HTTPS_PROXY": "http://aura-egress-proxy:3128"
            }
        elif req.network_profile == "open":
            network_mode = "bridge"

        image = self.image_map.get(req.language, self.image_map["python"])
        cmd = ["python", f"/work/{file_name}"] if req.language == "python" else ["node", f"/work/{file_name}"]

        container = None
        try:
            loop = asyncio.get_running_loop()
            docker_kwargs = self.constraints.to_docker_kwargs()
            docker_kwargs.update({
                "image": image,
                "command": ["timeout", str(req.timeout_s)] + cmd,
                "detach": True,
                "network_mode": network_mode,
                "environment": environment,
                "volumes": {str(run_dir): {"bind": "/work", "mode": "ro"}},
                "working_dir": "/work"
            })

            container = await loop.run_in_executor(
                None, lambda: self.docker_client.containers.run(**docker_kwargs)
            )

            status = await loop.run_in_executor(
                None, lambda: container.wait(timeout=req.timeout_s + 5)
            )
            stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
            stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
            exit_code = status.get("StatusCode", -1)

            return {
                "ok": exit_code == 0,
                "exit_code": exit_code,
                "stdout": stdout[:64000],
                "stderr": stderr[:64000],
                "error": None if exit_code == 0 else f"Process exited with status {exit_code}",
                "engine": "docker-cgroup"
            }

        except Exception as e:
            return {"ok": False, "exit_code": -1, "stdout": "", "stderr": "", "error": f"Container execution failed: {str(e)}"}
        finally:
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
            shutil.rmtree(run_dir, ignore_errors=True)

    async def _execute_local_isolated(self, req: ExecutionRequest) -> Dict[str, Any]:
        """
        Isolated local runner with ephemeral directory, timeouts, and env scrubbing.
        Used for local development when Docker daemon is not active.
        """
        run_dir = BASE_RUN_DIR / req.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        file_name = "main.py" if req.language == "python" else "index.js"
        source_path = run_dir / file_name
        source_path.write_text(req.code, encoding="utf-8")

        # Command selection
        if req.language == "python":
            cmd = [sys.executable, str(source_path)]
        elif req.language in ["node", "javascript", "js"]:
            cmd = ["node", str(source_path)]
        else:
            return {"ok": False, "exit_code": -1, "stdout": "", "stderr": f"Unsupported language: {req.language}", "error": "Unsupported language"}

        # Sanitized isolated environment
        safe_env = {
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", "C:\\Windows"),
            "PATH": os.environ.get("PATH", ""),
            "TEMP": str(run_dir),
            "TMP": str(run_dir),
            "PYTHONPATH": ""
        }

        try:
            loop = asyncio.get_running_loop()
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(run_dir),
                env=safe_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                stdout_data, stderr_data = await asyncio.wait_for(proc.communicate(), timeout=req.timeout_s)
                exit_code = proc.returncode
                stdout_str = stdout_data.decode("utf-8", errors="replace")
                stderr_str = stderr_data.decode("utf-8", errors="replace")

                return {
                    "ok": exit_code == 0,
                    "exit_code": exit_code,
                    "stdout": stdout_str[:64000],
                    "stderr": stderr_str[:64000],
                    "error": None if exit_code == 0 else f"Process exited with status {exit_code}",
                    "engine": "local-isolated"
                }
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except Exception:
                    pass
                return {
                    "ok": False,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": f"Execution timed out after {req.timeout_s}s",
                    "error": "Timeout",
                    "engine": "local-isolated"
                }

        except Exception as e:
            return {"ok": False, "exit_code": -1, "stdout": "", "stderr": "", "error": str(e), "engine": "local-isolated"}
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

async def main():
    broker = SandboxBroker()
    server, bind_addr = await create_ipc_server(broker.handle_client, socket_path=SOCKET_PATH)
    logger.info(f"Sandbox Broker successfully listening on: {bind_addr}")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
