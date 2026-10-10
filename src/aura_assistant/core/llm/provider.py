"""
Aura Assistant - Ollama Asynchronous LLM Provider
Handles streaming inferences, embeddings, shared HTTP connection pooling,
runtime telemetry logging, and automatic local fallback simulation
when Ollama is unreachable or model is not yet pulled.
"""

import os
import json
import time
import logging
import httpx
from typing import AsyncGenerator, Dict, Any, List, Optional, Union, Callable

# Enable FlashAttention-2 and KV Cache Quantization defaults for child processes if applicable
os.environ.setdefault("OLLAMA_FLASH_ATTENTION", "1")
os.environ.setdefault("OLLAMA_KV_CACHE_TYPE", "q8_0")

logger = logging.getLogger("aura-llm-provider")


class OllamaProvider:
    def __init__(
        self,
        host: str = "http://127.0.0.1:11434",
        http_client: Optional[httpx.AsyncClient] = None,
        on_model_missing: Optional[Callable[[str], None]] = None
    ):
        self.host = host.rstrip("/")
        self.nim_base_url = os.environ.get("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
        self.is_offline_simulation = False
        self._health_valid_until: float = 0.0
        self._offline_backoff_until: float = 0.0
        self._shared_client: Optional[httpx.AsyncClient] = http_client
        self._client_loop: Optional[ Any ] = None
        self._owns_client: bool = http_client is None
        self.on_model_missing = on_model_missing
        self.last_usage_metrics: Dict[str, Any] = {}
        self.last_response_source: str = "live_model"
        self.last_submitted_messages: List[Dict[str, str]] = []

    def _get_client(self) -> httpx.AsyncClient:
        import asyncio
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if (
            self._shared_client is None
            or self._shared_client.is_closed
            or (self._client_loop is not None and current_loop is not None and self._client_loop is not current_loop)
        ):
            self._shared_client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=2.5, read=120.0, write=10.0, pool=5.0),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=50)
            )
            self._client_loop = current_loop
            self._owns_client = True
        elif self._client_loop is None and current_loop is not None:
            self._client_loop = current_loop
        return self._shared_client

    async def aclose(self) -> None:
        """Closes the HTTP client only if owned by this provider instance during shutdown."""
        if self._owns_client and self._shared_client is not None and not self._shared_client.is_closed:
            try:
                await self._shared_client.aclose()
            except Exception:
                pass


    async def check_health(self, force: bool = False) -> bool:
        """
        Checks if local Ollama daemon is reachable.
        Caches healthy status for 30s and offline status for 5s (fast-fail backoff).
        """
        now = time.time()
        if not force:
            if now < self._health_valid_until:
                return True
            if now < self._offline_backoff_until:
                return False

        client = self._get_client()
        try:
            res = await client.get(f"{self.host}/api/tags", timeout=2.0)
            if res.status_code == 200:
                self._health_valid_until = now + 30.0
                self._offline_backoff_until = 0.0
                self.is_offline_simulation = False
                return True
            self._offline_backoff_until = now + 5.0
            self.is_offline_simulation = True
            return False
        except Exception:
            self._health_valid_until = 0.0
            self._offline_backoff_until = now + 5.0
            self.is_offline_simulation = True
            return False

    async def stream_nvidia_nim(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 2048
    ) -> AsyncGenerator[str, None]:
        """
        Streams tokens from NVIDIA NIM Microservices for Nemotron 3 Ultra (550B / 1M Context).
        Seamlessly falls back to local sovereign inference if NVIDIA_API_KEY is not configured.
        """
        api_key = os.environ.get("NVIDIA_API_KEY") or os.environ.get("AURA_NIM_API_KEY")
        if not api_key:
            logger.info(f"NVIDIA_API_KEY not set for '{model}'. Accelerating on local sovereign engine.")
            async for tok in self.stream_chat("qwen2.5:0.5b", messages, temperature, num_ctx=2048, keep_alive=-1):
                yield tok
            return

        nim_model = model if "/" in model else "nvidia/nemotron-3-ultra"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "text/event-stream",
            "Content-Type": "application/json"
        }
        payload = {
            "model": nim_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True
        }

        client = self._get_client()
        try:
            async with client.stream(
                "POST",
                f"{self.nim_base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=60.0
            ) as resp:
                if resp.status_code != 200:
                    logger.warning(f"NVIDIA NIM returned {resp.status_code}. Falling back to local sovereign engine.")
                    async for tok in self.stream_chat("qwen2.5:0.5b", messages, temperature, num_ctx=2048, keep_alive=-1):
                        yield tok
                    return

                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                    except json.JSONDecodeError:
                        continue
                self.last_response_source = "live_model"
        except Exception as e:
            logger.warning(f"NVIDIA NIM stream error ({e}). Falling back to local sovereign engine.")
            async for tok in self.stream_chat("qwen2.5:0.5b", messages, temperature, num_ctx=2048, keep_alive=-1):
                yield tok

    async def stream_chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        num_ctx: int = 2048,
        keep_alive: Union[int, str] = "10m",
        num_predict: Optional[int] = None
    ) -> AsyncGenerator[str, None]:
        """
        Streams tokens from NVIDIA NIM (if Nemotron Ultra selected) or local Ollama chat API.
        Uses the authoritative num_ctx and keep_alive resolved by LLMRouter.
        """
        self.last_submitted_messages = list(messages)

        if "nemotron" in model.lower() or model.startswith("nvidia/"):
            async for tok in self.stream_nvidia_nim(model, messages, temperature):
                yield tok
            return

        is_alive = await self.check_health()
        if not is_alive:
            self.last_response_source = "offline_fallback"
            logger.warning(f"Ollama daemon unreachable at {self.host}. Streaming simulation response.")
            simulated_text = (
                f"[Aura Local Mode] Processed request using local fallback for model '{model}'. "
                f"Workspace ready. Standing by for commands."
            )
            for token in simulated_text.split(" "):
                yield token + " "
            return

        self.last_response_source = "live_model"
        effective_predict = num_predict or (1024 if num_ctx >= 16384 else 512)

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "think": False,
            "keep_alive": keep_alive,
            "options": {
                "temperature": temperature,
                "num_ctx": num_ctx,
                "num_batch": 512,
                "num_thread": 8,
                "num_predict": effective_predict,
                "use_mmap": True
            }
        }

        client = self._get_client()
        t_start = time.perf_counter()
        first_token_ms: Optional[float] = None

        async with client.stream("POST", f"{self.host}/api/chat", json=payload, timeout=120.0) as response:
            if response.status_code != 200:
                err_body = await response.aread()
                err_text = err_body.decode("utf-8", errors="replace")
                if response.status_code == 404 or "not found" in err_text.lower():
                    if self.on_model_missing:
                        self.on_model_missing(model)
                    if model not in ("qwen2.5:0.5b", "qwen2.5:1.5b"):
                        fallback_model = "qwen2.5:0.5b"
                        logger.warning(
                            f"Model '{model}' not found in Ollama. Invalidating cache and falling back to '{fallback_model}'."
                        )
                        async for tok in self.stream_chat(fallback_model, messages, temperature, num_ctx=2048, keep_alive=-1):
                            yield tok
                        return
                    self.last_response_source = "offline_fallback"
                    logger.warning(f"Model '{model}' not yet pulled in Ollama. Streaming simulation fallback.")
                    simulated_text = (
                        f"[Aura Local Mode] Model '{model}' not yet pulled. "
                        f"Standing by in simulation mode."
                    )
                    for token in simulated_text.split(" "):
                        yield token + " "
                    return
                raise RuntimeError(f"Ollama error {response.status_code}: {err_text}")

            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    msg = chunk.get("message", {})
                    content = msg.get("content", "")
                    if content:
                        if first_token_ms is None:
                            first_token_ms = (time.perf_counter() - t_start) * 1000.0
                        yield content
                    if chunk.get("done"):
                        self.last_usage_metrics = {
                            "model": model,
                            "num_ctx": num_ctx,
                            "keep_alive": keep_alive,
                            "ttft_ms": round(first_token_ms or 0.0, 2),
                            "total_duration_ms": round(chunk.get("total_duration", 0) / 1e6, 2),
                            "load_duration_ms": round(chunk.get("load_duration", 0) / 1e6, 2),
                            "prompt_eval_count": chunk.get("prompt_eval_count", 0),
                            "eval_count": chunk.get("eval_count", 0)
                        }
                        logger.info(f"llm.usage {json.dumps(self.last_usage_metrics)}")
                except json.JSONDecodeError:
                    continue

    async def generate_embedding(self, text: str, model: str = "nomic-embed-text") -> List[float]:
        """Generates a text embedding vector (768-dim for nomic-embed-text) using the shared client."""
        is_alive = await self.check_health()
        if is_alive:
            client = self._get_client()
            try:
                resp = await client.post(
                    f"{self.host}/api/embeddings",
                    json={"model": model, "prompt": text},
                    timeout=30.0
                )
                if resp.status_code == 200:
                    data = resp.json()
                    emb = data.get("embedding", [])
                    if emb:
                        return emb
            except Exception as e:
                logger.debug(f"Embedding call failed ({e}); using deterministic hash fallback.")

        import hashlib
        import random
        seed = int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16)
        rng = random.Random(seed)
        return [rng.uniform(-1.0, 1.0) for _ in range(768)]
