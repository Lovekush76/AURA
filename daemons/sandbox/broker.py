#!/usr/bin/env python3
"""
Aura Assistant - Privileged Host Sandbox Broker
Listens on local IPC (Unix Domain Socket or Local Loopback) and executes code
inside strictly isolated Docker containers (with cgroup v2 enforcement)
with all blocking Docker SDK and filesystem operations offloaded to a bounded
ThreadPoolExecutor and guarded by an asyncio.Semaphore.
"""

import sys
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import shutil
import time
import uuid
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
    def __init__(
        self,
        max_concurrent_runs: int = 4,
        allow_local_fallback: Optional[bool] = None
    ):
        BASE_RUN_DIR.mkdir(parents=True, exist_ok=True)
        self.docker_client = None
        self.constraints = CgroupConstraints()
        self._concurrency_sem = asyncio.Semaphore(max_concurrent_runs)
        self._io_executor = ThreadPoolExecutor(
            max_workers=max_concurrent_runs,
            thread_name_prefix="aura-sandbox-io"
        )
        if allow_local_fallback is None:
            env_flag = os.environ.get("AURA_ALLOW_LOCAL_SANDBOX_FALLBACK", "1").strip().lower()
            self.allow_local_fallback = env_flag in ("1", "true", "yes")
        else:
            self.allow_local_fallback = allow_local_fallback

        if HAS_DOCKER:
            try:
                self.docker_client = docker.from_env(timeout=2)
                self.docker_client.ping()
                logger.info("Docker daemon verified. Using containerized cgroup sandbox.")
            except Exception as e:
                logger.warning(f"Docker unreachable ({e}). Operating in Local Process Isolation mode={self.allow_local_fallback}.")
                self.docker_client = None
        else:
            logger.warning("Docker package not found. Operating in Local Process Isolation mode.")

        self.image_map = {
            "python": "aura-sandbox-python:latest",
            "node": "aura-sandbox-node:latest"
        }

    def shutdown(self) -> None:
        self._io_executor.shutdown(wait=False)

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            raw_data = await reader.readuntil(b"\n")
            payload = json.loads(raw_data.decode().strip())

            req = ExecutionRequest(
                run_id=payload.get("run_id", str(uuid.uuid4())),
                language=payload.get("language", "python"),
                code=payload.get("code", ""),
                network_profile=payload.get("network_profile", "none"),
                timeout_s=max(1, min(60, int(payload.get("timeout_s", 20))))
            )

            result = await self._execute(req)
            writer.write(json.dumps(result).encode() + b"\n")
            await writer.drain()
        except Exception as e:
            logger.error(f"Error handling broker request: {e}")
            err_resp = {"ok": False, "exit_code": -1, "error": str(e), "stdout": "", "stderr": ""}
            writer.write(json.dumps(err_resp).encode() + b"\n")
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def _execute(self, req: ExecutionRequest) -> Dict[str, Any]:
        async with self._concurrency_sem:
            if self.docker_client:
                return await self._execute_docker(req)
            if not self.allow_local_fallback:
                return {
                    "ok": False,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": "Docker sandbox unavailable and local subprocess fallback is disabled by security policy.",
                    "error": "SandboxUnavailableError",
                    "engine": "none"
                }
            return await self._execute_local_isolated(req)

    @staticmethod
    def _prepare_run_dir_sync(run_dir: Path, file_name: str, code: str) -> Path:
        run_dir.mkdir(parents=True, exist_ok=True)
        source_path = run_dir / file_name
        source_path.write_text(code, encoding="utf-8")
        return source_path

    @staticmethod
    def _cleanup_docker_and_dir_sync(container: Any, run_dir: Path) -> None:
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:
                pass
        shutil.rmtree(run_dir, ignore_errors=True)

    async def _execute_docker(self, req: ExecutionRequest) -> Dict[str, Any]:
        t0 = time.perf_counter()
        loop = asyncio.get_running_loop()
        run_dir = BASE_RUN_DIR / req.run_id
        file_name = "main.py" if req.language == "python" else "index.js"

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
            await loop.run_in_executor(
                self._io_executor,
                self._prepare_run_dir_sync,
                run_dir,
                file_name,
                req.code
            )

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

            t_start_container = time.perf_counter()
            container = await loop.run_in_executor(
                self._io_executor,
                lambda: self.docker_client.containers.run(**docker_kwargs)
            )
            startup_ms = (time.perf_counter() - t_start_container) * 1000.0

            def _wait_and_collect_logs():
                status = container.wait(timeout=req.timeout_s + 5)
                out_bytes = container.logs(stdout=True, stderr=False) or b""
                err_bytes = container.logs(stdout=False, stderr=True) or b""
                return status, out_bytes, err_bytes

            status, out_bytes, err_bytes = await loop.run_in_executor(
                self._io_executor,
                _wait_and_collect_logs
            )
            stdout = out_bytes.decode("utf-8", errors="replace") if isinstance(out_bytes, bytes) else str(out_bytes)
            stderr = err_bytes.decode("utf-8", errors="replace") if isinstance(err_bytes, bytes) else str(err_bytes)
            exit_code = (status or {}).get("StatusCode", -1)
            total_ms = (time.perf_counter() - t0) * 1000.0

            return {
                "ok": exit_code == 0,
                "exit_code": exit_code,
                "stdout": stdout[:64000],
                "stderr": stderr[:64000],
                "error": None if exit_code == 0 else f"Process exited with status {exit_code}",
                "engine": "docker-cgroup",
                "startup_ms": round(startup_ms, 2),
                "total_ms": round(total_ms, 2)
            }

        except asyncio.CancelledError:
            raise
        except Exception as e:
            return {
                "ok": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "",
                "error": f"Container execution failed: {str(e)}",
                "engine": "docker-cgroup"
            }
        finally:
            await loop.run_in_executor(
                self._io_executor,
                self._cleanup_docker_and_dir_sync,
                container,
                run_dir
            )

    async def _execute_local_isolated(self, req: ExecutionRequest) -> Dict[str, Any]:
        """
        Isolated local runner with ephemeral directory, timeouts, env scrubbing,
        and off-event-loop directory cleanup.
        """
        t0 = time.perf_counter()
        loop = asyncio.get_running_loop()
        run_dir = BASE_RUN_DIR / req.run_id
        file_name = "main.py" if req.language == "python" else "index.js"

        if req.language == "python":
            cmd_prefix = [sys.executable, "-I"]
        elif req.language in ["node", "javascript", "js"]:
            cmd_prefix = ["node"]
        else:
            return {
                "ok": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Unsupported language: {req.language}",
                "error": "Unsupported language"
            }

        safe_env = {
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", "C:\\Windows"),
            "PATH": os.environ.get("PATH", ""),
            "TEMP": str(run_dir),
            "TMP": str(run_dir),
            "PYTHONPATH": "",
            "PYTHONNOUSERSITE": "1"
        }

        proc = None
        try:
            source_path = await loop.run_in_executor(
                self._io_executor,
                self._prepare_run_dir_sync,
                run_dir,
                file_name,
                req.code
            )
            cmd = cmd_prefix + [str(source_path)]

            t_spawn = time.perf_counter()
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(run_dir),
                env=safe_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            startup_ms = (time.perf_counter() - t_spawn) * 1000.0

            try:
                stdout_data, stderr_data = await asyncio.wait_for(proc.communicate(), timeout=req.timeout_s)
                exit_code = proc.returncode
                stdout_str = stdout_data.decode("utf-8", errors="replace")
                stderr_str = stderr_data.decode("utf-8", errors="replace")
                total_ms = (time.perf_counter() - t0) * 1000.0

                return {
                    "ok": exit_code == 0,
                    "exit_code": exit_code,
                    "stdout": stdout_str[:64000],
                    "stderr": stderr_str[:64000],
                    "error": None if exit_code == 0 else f"Process exited with status {exit_code}",
                    "engine": "local-isolated",
                    "startup_ms": round(startup_ms, 2),
                    "total_ms": round(total_ms, 2)
                }
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                    await proc.wait()
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

        except asyncio.CancelledError:
            if proc is not None and proc.returncode is None:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
            raise
        except Exception as e:
            return {
                "ok": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "",
                "error": str(e),
                "engine": "local-isolated"
            }
        finally:
            await loop.run_in_executor(
                self._io_executor,
                lambda: shutil.rmtree(run_dir, ignore_errors=True)
            )


async def main():
    broker = SandboxBroker()
    server, bind_addr = await create_ipc_server(broker.handle_client, socket_path=SOCKET_PATH)
    logger.info(f"Sandbox Broker successfully listening on: {bind_addr}")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
