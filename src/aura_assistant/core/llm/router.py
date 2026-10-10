"""
Aura Assistant - Multi-Model Intent Router & Unified Residency Gate
Manages model inventory caching (30s TTL + 5s offline backoff), runtime /api/ps verification,
serialized heavy-model swapping via asyncio.Lock, and authoritative per-route num_ctx / keep_alive.
"""

import asyncio
import time
import httpx
import logging
from typing import Dict, Any, Optional, Union, FrozenSet, List
from pydantic import BaseModel

logger = logging.getLogger("aura-llm-router")


class RouteResult(BaseModel):
    model: str
    num_ctx: int
    temperature: float
    pinned: bool
    keep_alive: Union[int, str] = "10m"
    reasoning_mode: bool = False
    fallback_reason: Optional[str] = None


class LLMRouter:
    def __init__(
        self,
        ollama_host: str = "http://127.0.0.1:11434",
        vram_arbiter: Any = None,
        http_client: Optional[httpx.AsyncClient] = None,
        cache_ttl_seconds: float = 30.0,
        offline_backoff_seconds: float = 5.0
    ):
        self.ollama_host = ollama_host.rstrip("/")
        self.vram_arbiter = vram_arbiter
        self.cache_ttl_seconds = cache_ttl_seconds
        self.offline_backoff_seconds = offline_backoff_seconds

        self._shared_client: Optional[httpx.AsyncClient] = http_client
        self._client_loop: Optional[Any] = None
        self._owns_client: bool = http_client is None
        self._tags_lock = asyncio.Lock()
        self._swap_lock = asyncio.Lock()

        self.slots: Dict[str, Dict[str, Any]] = {
            "voice": {"model": "qwen3.5:4b", "ctx": 1536, "temp": 0.4, "pinned": True, "keep_alive": -1},
            "chat": {"model": "qwen2.5:0.5b", "ctx": 2048, "temp": 0.5, "pinned": True, "keep_alive": -1},
            "chat_multi_turn": {"model": "qwen3.5:4b", "ctx": 4096, "temp": 0.3, "pinned": True, "keep_alive": -1},
            "code": {"model": "qwen3-coder:30b", "ctx": 32768, "temp": 0.2, "pinned": False, "keep_alive": "10m"},
            "reasoning": {"model": "deepseek-r1:14b", "ctx": 32768, "temp": 0.5, "pinned": False, "keep_alive": "10m"},
            "ultra": {"model": "nvidia/nemotron-3-ultra", "ctx": 1000000, "temp": 0.3, "pinned": False, "keep_alive": "10m"}
        }

        # Authoritative context limits for known models when selected via override_model
        self.model_ctx_profiles: Dict[str, Dict[str, Any]] = {
            "qwen2.5:0.5b": {"ctx": 2048, "temp": 0.5, "pinned": True, "keep_alive": -1, "reasoning": False},
            "qwen2.5:1.5b": {"ctx": 4096, "temp": 0.3, "pinned": True, "keep_alive": -1, "reasoning": False},
            "qwen3.5:4b": {"ctx": 4096, "temp": 0.3, "pinned": True, "keep_alive": -1, "reasoning": False},
            "qwen3-coder:30b": {"ctx": 32768, "temp": 0.2, "pinned": False, "keep_alive": "10m", "reasoning": False},
            "deepseek-r1:14b": {"ctx": 32768, "temp": 0.5, "pinned": False, "keep_alive": "10m", "reasoning": True},
        }

        self.current_heavy_model: Optional[str] = None
        self._cached_available_models: Optional[FrozenSet[str]] = None
        self._tags_valid_until: float = 0.0
        self._offline_backoff_until: float = 0.0
        self.daemon_reachable: bool = False

    def _get_client(self) -> httpx.AsyncClient:
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
                base_url=self.ollama_host,
                timeout=httpx.Timeout(connect=2.5, read=30.0, write=10.0, pool=5.0),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=50)
            )
            self._client_loop = current_loop
            self._owns_client = True
        elif self._client_loop is None and current_loop is not None:
            self._client_loop = current_loop
        return self._shared_client

    async def aclose(self) -> None:
        if self._owns_client and self._shared_client is not None and not self._shared_client.is_closed:
            try:
                await self._shared_client.aclose()
            except Exception:
                pass


    def invalidate_model_cache(self, missing_model: Optional[str] = None) -> None:
        """Explicitly invalidates the /api/tags model cache (e.g., after 404 or model pull)."""
        self._tags_valid_until = 0.0
        if missing_model and self._cached_available_models:
            base = missing_model[:-7] if missing_model.endswith(":latest") else missing_model
            filtered = {
                m for m in self._cached_available_models
                if m not in (missing_model, base, f"{base}:latest")
            }
            self._cached_available_models = frozenset(filtered)

    @staticmethod
    def _normalize_model_names(raw_names: set) -> FrozenSet[str]:
        normalized = set()
        for n in raw_names:
            if not n:
                continue
            normalized.add(n)
            if n.endswith(":latest"):
                normalized.add(n[:-7])
            elif ":" not in n:
                normalized.add(f"{n}:latest")
        return frozenset(normalized)

    async def get_available_models(self, force_refresh: bool = False) -> FrozenSet[str]:
        """
        Fetches models currently installed in Ollama (/api/tags).
        Uses a 30s TTL cache, 5s offline failure backoff, and asyncio.Lock to prevent stampedes.
        Returns an immutable frozenset.
        """
        now = time.time()
        if not force_refresh:
            if self._cached_available_models is not None and now < self._tags_valid_until:
                return self._cached_available_models
            if now < self._offline_backoff_until:
                return self._cached_available_models or frozenset()

        async with self._tags_lock:
            now = time.time()
            if not force_refresh:
                if self._cached_available_models is not None and now < self._tags_valid_until:
                    return self._cached_available_models
                if now < self._offline_backoff_until:
                    return self._cached_available_models or frozenset()

            client = self._get_client()
            try:
                url = "/api/tags" if client.base_url else f"{self.ollama_host}/api/tags"
                resp = await client.get(url, timeout=2.0)
                if resp.status_code == 200:
                    data = resp.json() if callable(getattr(resp, "json", None)) else {}
                    if asyncio.iscoroutine(data):
                        data = await data
                    models = (data or {}).get("models", [])
                    names = {m.get("name") for m in models if isinstance(m, dict) and m.get("name")}
                    self._cached_available_models = self._normalize_model_names(names)
                    self._tags_valid_until = time.time() + self.cache_ttl_seconds
                    self._offline_backoff_until = 0.0
                    self.daemon_reachable = True
                    return self._cached_available_models
                self._offline_backoff_until = time.time() + self.offline_backoff_seconds
                self.daemon_reachable = False
            except Exception as e:
                logger.debug(f"Could not fetch available models from Ollama: {e}")
                self._offline_backoff_until = time.time() + self.offline_backoff_seconds
                self.daemon_reachable = False

            return self._cached_available_models or frozenset()

    async def get_running_models(self) -> List[Dict[str, Any]]:
        """Queries Ollama /api/ps for actual currently loaded models and updates VRAMArbiter."""
        if time.time() < self._offline_backoff_until:
            return []
        client = self._get_client()
        try:
            url = "/api/ps" if client.base_url else f"{self.ollama_host}/api/ps"
            resp = await client.get(url, timeout=2.0)
            if resp.status_code == 200:
                data = resp.json() if callable(getattr(resp, "json", None)) else {}
                if asyncio.iscoroutine(data):
                    data = await data
                models = (data or {}).get("models", [])
                if isinstance(models, list):
                    if self.vram_arbiter is not None:
                        self.vram_arbiter.update_from_runtime_ps(models)
                    return models
        except Exception as e:
            logger.debug(f"Could not query /api/ps: {e}")
        return []

    async def warm_pinned_models(self) -> bool:
        """Pins the fast voice model into VRAM/RAM upon system startup."""
        voice_cfg = self.slots["voice"]
        logger.info(f"Locking primary voice model '{voice_cfg['model']}' into memory...")
        client = self._get_client()
        try:
            url = "/api/generate" if client.base_url else f"{self.ollama_host}/api/generate"
            resp = await client.post(
                url,
                json={"model": voice_cfg["model"], "keep_alive": -1},
                timeout=10.0
            )
            if resp.status_code == 200:
                logger.info("Voice model successfully locked into memory.")
                return True
        except Exception as e:
            logger.info(f"Background pre-warm skipped (daemon offline or booting): {e}")
            self._offline_backoff_until = time.time() + self.offline_backoff_seconds
        return False

    def _select_best_fallback(self, available: FrozenSet[str], channel: str) -> Dict[str, Any]:
        """Selects a supported pinned fallback model that is verified installed."""
        voice_cfg = self.slots["voice"]
        chat_cfg = self.slots["chat"]
        if channel == "voice":
            if not available or voice_cfg["model"] in available:
                return voice_cfg
            if chat_cfg["model"] in available:
                return chat_cfg
            return voice_cfg
        if not available or voice_cfg["model"] in available:
            return {"model": voice_cfg["model"], "ctx": 4096, "temp": 0.4, "pinned": True, "keep_alive": -1}
        if chat_cfg["model"] in available:
            return chat_cfg
        return chat_cfg

    async def _admit_and_resolve_route(
        self,
        target_model: str,
        num_ctx: int,
        temperature: float,
        pinned: bool,
        keep_alive: Union[int, str],
        reasoning_mode: bool,
        available: FrozenSet[str],
        channel: str
    ) -> RouteResult:
        """
        Unified admission & residency gate for all routes (automatic and override_model).
        Checks model inventory availability and VRAM/memory residency before returning.
        """
        # 1. Cloud / NVIDIA NIM route bypasses local Ollama residency
        if "nemotron" in target_model.lower() or target_model.startswith("nvidia/"):
            ultra_cfg = self.slots["ultra"]
            return RouteResult(
                model=target_model if "/" in target_model else ultra_cfg["model"],
                num_ctx=ultra_cfg["ctx"],
                temperature=ultra_cfg["temp"],
                pinned=False,
                keep_alive=ultra_cfg["keep_alive"],
                reasoning_mode=True
            )

        # 2. Verify model is installed in local Ollama (if inventory is known/non-empty)
        if available and target_model not in available:
            fb = self._select_best_fallback(available, channel)
            reason = f"requested_model_not_installed:{target_model}"
            logger.info(f"Model '{target_model}' not in Ollama /api/tags; routing to '{fb['model']}' ({reason}).")
            return RouteResult(
                model=fb["model"],
                num_ctx=fb["ctx"],
                temperature=fb["temp"],
                pinned=fb["pinned"],
                keep_alive=fb["keep_alive"],
                reasoning_mode=reasoning_mode,
                fallback_reason=reason
            )

        # 3. Pinned models are pre-admitted with keep_alive=-1
        if pinned:
            return RouteResult(
                model=target_model,
                num_ctx=num_ctx,
                temperature=temperature,
                pinned=True,
                keep_alive=-1,
                reasoning_mode=reasoning_mode
            )

        # 4. Heavy / non-pinned models must pass serialized residency admission
        admitted = await self._ensure_heavy_residency(target_model, num_ctx=num_ctx, keep_alive=keep_alive)
        if not admitted:
            fb = self._select_best_fallback(available, channel)
            reason = f"residency_admission_rejected:{target_model}"
            logger.warning(f"Residency admission rejected '{target_model}'; falling back to '{fb['model']}'.")
            return RouteResult(
                model=fb["model"],
                num_ctx=fb["ctx"],
                temperature=fb["temp"],
                pinned=fb["pinned"],
                keep_alive=fb["keep_alive"],
                reasoning_mode=reasoning_mode,
                fallback_reason=reason
            )

        return RouteResult(
            model=target_model,
            num_ctx=num_ctx,
            temperature=temperature,
            pinned=False,
            keep_alive=keep_alive,
            reasoning_mode=reasoning_mode
        )

    async def resolve_route(
        self,
        prompt: str,
        channel: str = "text",
        override_model: Optional[str] = None,
        has_history: bool = False
    ) -> RouteResult:
        t0 = time.perf_counter()
        available = await self.get_available_models()

        # 1. Explicit UI or API override_model goes through the exact same residency & context gate
        if override_model and override_model != "auto":
            if "nemotron" in override_model.lower() or override_model.startswith("nvidia/"):
                ultra_cfg = self.slots["ultra"]
                res = await self._admit_and_resolve_route(
                    target_model=override_model,
                    num_ctx=ultra_cfg["ctx"],
                    temperature=ultra_cfg["temp"],
                    pinned=False,
                    keep_alive=ultra_cfg["keep_alive"],
                    reasoning_mode=True,
                    available=available,
                    channel=channel
                )
            else:
                base_override = override_model[:-7] if override_model.endswith(":latest") else override_model
                profile = self.model_ctx_profiles.get(
                    base_override,
                    {"ctx": 4096, "temp": 0.5, "pinned": False, "keep_alive": "10m", "reasoning": False}
                )
                effective_ctx = self.slots["voice"]["ctx"] if channel == "voice" and profile["pinned"] else profile["ctx"]
                res = await self._admit_and_resolve_route(
                    target_model=override_model,
                    num_ctx=effective_ctx,
                    temperature=profile["temp"],
                    pinned=profile["pinned"],
                    keep_alive=profile["keep_alive"],
                    reasoning_mode=profile["reasoning"],
                    available=available,
                    channel=channel
                )
            logger.debug(f"route.resolved model={res.model} ctx={res.num_ctx} latency_ms={(time.perf_counter()-t0)*1000:.2f}")
            return res

        # 2. Modality enforcement: Voice channel must never experience cold model swaps
        if channel == "voice":
            cfg = self.slots["voice"]
            res = await self._admit_and_resolve_route(
                target_model=cfg["model"],
                num_ctx=cfg["ctx"],
                temperature=cfg["temp"],
                pinned=True,
                keep_alive=-1,
                reasoning_mode=False,
                available=available,
                channel=channel
            )
            return res

        # 3. Structural intent detection for coding
        code_markers = ["def ", "class ", "import ", "function(", "const ", "SELECT ", "curl ", "npm ", "```"]
        if any(marker in prompt for marker in code_markers) or "write a script" in prompt.lower():
            cfg = self.slots["code"]
            return await self._admit_and_resolve_route(
                target_model=cfg["model"],
                num_ctx=cfg["ctx"],
                temperature=cfg["temp"],
                pinned=False,
                keep_alive=cfg["keep_alive"],
                reasoning_mode=False,
                available=available,
                channel=channel
            )

        # 4. Algorithmic reasoning and problem solving detection
        lower_p = prompt.lower()
        reasoning_markers = [
            "prove", "analyze complexity", "architect", "deep analysis",
            "step by step", "algorithm", "derive", "calculate", "solve",
            "why does", "explain why", "deduce", "logic", "troubleshoot",
            "root cause", "system design"
        ]
        if any(w in lower_p for w in reasoning_markers):
            cfg = self.slots["reasoning"]
            return await self._admit_and_resolve_route(
                target_model=cfg["model"],
                num_ctx=cfg["ctx"],
                temperature=cfg["temp"],
                pinned=False,
                keep_alive=cfg["keep_alive"],
                reasoning_mode=True,
                available=available,
                channel=channel
            )

        # 5. Multi-turn, analytical, or instruction-sensitive conversational routing (P2-8)
        instruction_sensitive_markers = [
            "reply with", "exact", "previous", "earlier", "what did you",
            "what did i", "explain", "compare", "summarize", "diagnos",
            "telemetry", "cache", "history", "context", "table", "verify",
            "audit", "recall", "remember"
        ]
        needs_strong_chat = (
            has_history
            or len(prompt.strip()) > 80
            or any(m in lower_p for m in instruction_sensitive_markers)
        )
        if needs_strong_chat:
            strong_cfg = dict(self.slots["chat_multi_turn"])
            if available and strong_cfg["model"] not in available and "qwen2.5:1.5b" in available:
                strong_cfg["model"] = "qwen2.5:1.5b"
            if self.vram_arbiter is None or self.vram_arbiter.can_load_model(strong_cfg["model"], num_ctx=strong_cfg["ctx"]):
                return await self._admit_and_resolve_route(
                    target_model=strong_cfg["model"],
                    num_ctx=strong_cfg["ctx"],
                    temperature=strong_cfg["temp"],
                    pinned=True,
                    keep_alive=-1,
                    reasoning_mode=False,
                    available=available,
                    channel=channel
                )

        # 6. Low-stakes, short single-turn conversation or constrained fallback
        cfg = self.slots["chat"]
        return await self._admit_and_resolve_route(
            target_model=cfg["model"],
            num_ctx=cfg["ctx"],
            temperature=cfg["temp"],
            pinned=True,
            keep_alive=-1,
            reasoning_mode=False,
            available=available,
            channel=channel
        )

    async def _ensure_heavy_residency(
        self,
        target_model: str,
        num_ctx: int = 32768,
        keep_alive: Union[int, str] = "10m"
    ) -> bool:
        """
        Safely swaps heavy models under an asyncio.Lock via VRAMArbiter without evicting
        pinned voice/chat models. Returns True if admitted and ready, False otherwise.
        """
        async with self._swap_lock:
            await self.get_running_models()

            evicted_by_arbiter = None
            if self.vram_arbiter is not None:
                if not self.vram_arbiter.can_load_model(target_model, num_ctx=num_ctx):
                    logger.warning(f"VRAMArbiter rejected {target_model} (exceeds {self.vram_arbiter.vram_ceiling_mb} MiB ceiling).")
                    return False
                evicted_by_arbiter = self.vram_arbiter.notify_model_requested(target_model, num_ctx=num_ctx)

            if self.current_heavy_model == target_model:
                return True

            model_to_unload = evicted_by_arbiter or self.current_heavy_model
            client = self._get_client()
            gen_url = "/api/generate" if client.base_url else f"{self.ollama_host}/api/generate"

            try:
                if model_to_unload and model_to_unload != target_model:
                    logger.info(f"Unloading previous heavy model: {model_to_unload}")
                    unload_resp = await client.post(
                        gen_url,
                        json={"model": model_to_unload, "keep_alive": 0},
                        timeout=15.0
                    )
                    if unload_resp.status_code != 200:
                        logger.warning(f"Failed to unload {model_to_unload} (HTTP {unload_resp.status_code}).")
                        return False
                    if self.vram_arbiter is not None:
                        self.vram_arbiter.confirm_model_unloaded(model_to_unload)

                logger.info(f"Pre-warming heavy slot model: {target_model} (keep_alive={keep_alive})")
                warm_resp = await client.post(
                    gen_url,
                    json={"model": target_model, "keep_alive": keep_alive},
                    timeout=30.0
                )
                if warm_resp.status_code != 200:
                    logger.warning(f"Failed to pre-warm heavy model {target_model} (HTTP {warm_resp.status_code}).")
                    if self.vram_arbiter is not None:
                        self.vram_arbiter.confirm_model_unloaded(target_model)
                    return False

                self.current_heavy_model = target_model
                return True
            except Exception as e:
                logger.warning(f"Could not swap/pre-warm heavy model {target_model}: {e}")
                if self.vram_arbiter is not None:
                    self.vram_arbiter.confirm_model_unloaded(target_model)
                return False
