"""
Aura Assistant - Cross-Platform IPC Communication Layer
Handles transparent inter-process communication across Linux (Unix domain sockets)
and Windows (AF_UNIX or Loopback TCP fallback).
"""

import sys
import os
import asyncio
import logging
from pathlib import Path
from typing import Tuple, Optional, Callable, Awaitable

logger = logging.getLogger("aura-ipc")

DEFAULT_SANDBOX_SOCKET = "/run/aura/sandbox.sock" if sys.platform != "win32" else str(Path.home() / ".aura" / "sandbox.sock")
DEFAULT_TCP_FALLBACK_PORT = 8100

def get_socket_path(env_var: str, default_unix_path: str) -> str:
    override = os.environ.get(env_var)
    if override:
        return override
    if sys.platform != "win32":
        return default_unix_path
    # On Windows, keep socket in user home or local app data
    win_sock_dir = Path.home() / ".aura"
    win_sock_dir.mkdir(parents=True, exist_ok=True)
    return str(win_sock_dir / Path(default_unix_path).name)

async def create_ipc_server(
    client_handler: Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]],
    socket_path: str,
    tcp_fallback_port: int = DEFAULT_TCP_FALLBACK_PORT
) -> Tuple[asyncio.Server, str]:
    """
    Creates an IPC server. Tries Unix domain socket first. If on Windows and AF_UNIX is unsupported,
    transparently falls back to local loopback TCP.
    """
    try:
        # Check if Unix Domain Socket can be created
        sock_p = Path(socket_path)
        sock_p.parent.mkdir(parents=True, exist_ok=True)
        if sock_p.exists():
            try:
                sock_p.unlink()
            except Exception:
                pass

        server = await asyncio.start_unix_server(client_handler, path=socket_path)
        if sys.platform != "win32":
            try:
                os.chmod(socket_path, 0o660)
            except Exception:
                pass
        logger.info(f"IPC Server bound to Unix Domain Socket: {socket_path}")
        return server, f"unix://{socket_path}"
    except (AttributeError, NotImplementedError, OSError) as e:
        logger.warning(f"Unix socket binding failed ({e}). Falling back to Loopback TCP on 127.0.0.1:{tcp_fallback_port}")
        server = await asyncio.start_server(client_handler, host="127.0.0.1", port=tcp_fallback_port)
        logger.info(f"IPC Server bound to Loopback TCP: 127.0.0.1:{tcp_fallback_port}")
        return server, f"tcp://127.0.0.1:{tcp_fallback_port}"

async def connect_ipc_client(
    socket_path: str,
    tcp_fallback_port: int = DEFAULT_TCP_FALLBACK_PORT
) -> Tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """
    Connects to the IPC server via Unix domain socket or Loopback TCP fallback.
    """
    # 1. Try Unix domain socket
    try:
        if Path(socket_path).exists() or sys.platform != "win32":
            return await asyncio.open_unix_connection(path=socket_path)
    except (AttributeError, NotImplementedError, OSError, FileNotFoundError):
        pass

    # 2. Try TCP fallback
    return await asyncio.open_connection(host="127.0.0.1", port=tcp_fallback_port)
