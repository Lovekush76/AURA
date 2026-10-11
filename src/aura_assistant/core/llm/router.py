"""
Aura Assistant - Multi-Model Intent Router & Unified Residency Gate
Manages model inventory caching (30s TTL + 5s offline backoff), runtime /api/ps verification,
serialized heavy-model swapping via asyncio.Lock, and authoritative per-route num_ctx / keep_alive.
"""

import asyncio
import re
import time
import httpx
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union, FrozenSet, List
from pydantic import BaseModel
import yaml

logger = logging.getLogger("aura-llm-router")


class RouteResult(BaseModel):
    model: str
    num_ctx: int
    temperature: float
    pinned: bool
    keep_alive: Union[int, str] = "10m"
    reasoning_mode: bool = False
    fallback_reason: Optional[str] = None
    num_predict: int = 128
    num_thread: int = 4
    num_batch: int = 512
    query_scope: str = "standard"


class LLMRouter:
    def __init__(
        self,
        ollama_host: str = "http://127.0.0.1:11434",
        vram_arbiter: Any = None,
        http_client: Optional[httpx.AsyncClient] = None,
        cache_ttl_seconds: float = 30.0,
        offline_backoff_seconds: float = 5.0,
        config_path: Optional[str] = None
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

        self.output_budgets: Dict[str, int] = {
            "simple_factual": 512,
            "standard_technical": 768,
            "broad_overview": 1536,
            "long_form": 2048,
            "code_generation": 1024,
            "reasoning_deep": 1536,
            "recall": 128
        }

        self.slots: Dict[str, Dict[str, Any]] = {
            "voice": {"model": "qwen3.5:4b", "ctx": 1536, "temp": 0.4, "pinned": True, "keep_alive": -1, "predict": 96, "threads": 4, "batch": 512},
            "chat": {"model": "qwen2.5:0.5b", "ctx": 2048, "temp": 0.5, "pinned": True, "keep_alive": -1, "predict": 128, "threads": 4, "batch": 512},
            "technical": {"model": "qwen2.5:1.5b", "ctx": 4096, "temp": 0.4, "pinned": True, "keep_alive": -1, "predict": 512, "threads": 4, "batch": 512},
            "chat_moderate": {"model": "qwen2.5:1.5b", "ctx": 4096, "temp": 0.4, "pinned": True, "keep_alive": -1, "predict": 256, "threads": 4, "batch": 512},
            "code": {"model": "qwen3-coder:30b", "ctx": 32768, "temp": 0.2, "pinned": False, "keep_alive": "10m", "predict": 1024, "threads": 6, "batch": 512},
            "reasoning": {"model": "deepseek-r1:14b", "ctx": 32768, "temp": 0.5, "pinned": False, "keep_alive": "10m", "predict": 1024, "threads": 6, "batch": 512},
            "ultra": {"model": "nvidia/nemotron-3-ultra", "ctx": 1000000, "temp": 0.3, "pinned": False, "keep_alive": "10m", "predict": 2048, "threads": 4, "batch": 512}
        }

        # Dynamically load overrides from models.yaml if available
        self._load_config(config_path)

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

    def _load_config(self, config_path: Optional[str] = None) -> None:
        """Parses configs/models.yaml to populate slot models and residency attributes."""
        path_to_try = Path(config_path) if config_path else Path(__file__).resolve().parents[4] / "configs" / "models.yaml"
        if not path_to_try.exists():
            return
        try:
            with open(path_to_try, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            routing_cfg = data.get("routing", {})
            for slot_key, slot_info in routing_cfg.items():
                if isinstance(slot_info, dict) and "primary" in slot_info:
                    primary_model = slot_info["primary"]
                    if slot_key in self.slots:
                        self.slots[slot_key]["model"] = primary_model
                    elif slot_key == "chat":
                        self.slots["chat"]["model"] = primary_model

            out_cfg = data.get("output_budget", {})
            if isinstance(out_cfg, dict):
                for k, v in out_cfg.items():
                    if isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit()):
                        self.output_budgets[k] = int(v)

            logger.debug(f"Loaded dynamic models config and output budgets from {path_to_try}")
        except Exception as e:
            logger.warning(f"Could not load models config from {path_to_try}: {e}")

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
                url = "/api/tags" if client.base_url.scheme else f"{self.ollama_host}/api/tags"
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
            url = "/api/ps" if client.base_url.scheme else f"{self.ollama_host}/api/ps"
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

    async def warm_pinned_models(self, warm_chat: bool = False) -> bool:
        """Pins the fast primary chat and voice models into host RAM/VRAM upon system startup."""
        models_to_warm = [self.slots["voice"]["model"]]
        if warm_chat and self.slots["chat"]["model"] not in models_to_warm:
            models_to_warm.append(self.slots["chat"]["model"])

        client = self._get_client()
        success = False
        for m in models_to_warm:
            logger.info(f"Locking primary low-latency model '{m}' into memory...")
            try:
                url = "/api/generate" if client.base_url.scheme else f"{self.ollama_host}/api/generate"
                resp = await client.post(
                    url,
                    json={"model": m, "keep_alive": -1},
                    timeout=10.0
                )
                if resp.status_code == 200:
                    logger.info(f"Model '{m}' successfully locked into memory.")
                    success = True
            except Exception as e:
                logger.info(f"Pre-warm skipped for '{m}' (daemon offline or booting): {e}")
                self._offline_backoff_until = time.time() + self.offline_backoff_seconds
        return success

    def _select_best_fallback(self, available: FrozenSet[str], channel: str) -> Dict[str, Any]:
        """Selects a supported pinned fallback model that is verified installed."""
        chat_cfg = self.slots["chat"]
        voice_cfg = self.slots["voice"]
        if channel == "voice":
            if not available or voice_cfg["model"] in available:
                return voice_cfg
            if chat_cfg["model"] in available:
                return chat_cfg
            return voice_cfg

        # Text channel fallback when heavy model or requested model cannot be admitted:
        # Fall back to voice/strong pinned model (qwen3.5:4b) if installed, else moderate, else chat_cfg
        if not available or voice_cfg["model"] in available:
            return {"model": voice_cfg["model"], "ctx": 4096, "temp": 0.4, "pinned": True, "keep_alive": -1, "predict": 256, "threads": 4, "batch": 512}
        if "qwen2.5:1.5b" in available:
            return {"model": "qwen2.5:1.5b", "ctx": 4096, "temp": 0.4, "pinned": True, "keep_alive": -1, "predict": 256, "threads": 4, "batch": 512}
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
        channel: str,
        num_predict: int = 128,
        num_thread: int = 4,
        num_batch: int = 512,
        query_scope: str = "standard"
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
                reasoning_mode=True,
                num_predict=num_predict,
                num_thread=num_thread,
                num_batch=num_batch,
                query_scope=query_scope
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
                fallback_reason=reason,
                num_predict=num_predict,
                num_thread=num_thread,
                num_batch=num_batch,
                query_scope=query_scope
            )

        # 3. Pinned models are pre-admitted with keep_alive=-1
        if pinned:
            return RouteResult(
                model=target_model,
                num_ctx=num_ctx,
                temperature=temperature,
                pinned=True,
                keep_alive=-1,
                reasoning_mode=reasoning_mode,
                num_predict=num_predict,
                num_thread=num_thread,
                num_batch=num_batch,
                query_scope=query_scope
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
                fallback_reason=reason,
                num_predict=num_predict,
                num_thread=num_thread,
                num_batch=num_batch,
                query_scope=query_scope
            )

        return RouteResult(
            model=target_model,
            num_ctx=num_ctx,
            temperature=temperature,
            pinned=False,
            keep_alive=keep_alive,
            reasoning_mode=reasoning_mode,
            num_predict=num_predict,
            num_thread=num_thread,
            num_batch=num_batch,
            query_scope=query_scope
        )

    @staticmethod
    def classify_technical_intent(prompt: str, active_topic: Optional[str] = None) -> bool:
        """
        Lightweight intent classifier for technical programming concepts, language specifications,
        and follow-up questions referencing technical topics.
        """
        lower = prompt.lower().strip()
        technical_terms = [
            "inheritance", "polymorphism", "encapsulation", "abstraction",
            "interface", "interfaces", "abstract class", "abstract classes",
            "sql join", "inner join", "left join", "right join", "outer join", "foreign key",
            "dependency injection", "inversion of control", "design pattern", "singleton",
            "primitive type", "primitive types", "data type", "data types",
            "what is java", "what is python", "what is c++", "what is rust", "what is go",
            "binary tree", "hashmap", "linked list", "recursion",
            "concurrency", "multithreading", "garbage collection",
            "machine learning", "oop", "oop concepts"
        ]
        for term in technical_terms:
            if re.search(rf"\b{re.escape(term)}\b", lower):
                return True

        if active_topic:
            follow_up_patterns = [
                r"\bits\s+(type|types|syntax|features|properties|use|purpose)\b",
                r"\bhow\s+(does\s+it\s+work|to\s+use\s+it)\b",
                r"\b(types?|syntax|examples?|difference|pros\s+and\s+cons)\b",
                r"\bexplain\s+it\b",
                r"\bwhat\s+about\s+it\b",
                r"\bshow\s+an\s+example\b"
            ]
            for pat in follow_up_patterns:
                if re.search(pat, lower):
                    return True

        return False

    def classify_query_scope(self, prompt: str, active_topic: Optional[str] = None) -> str:
        """
        Classifies prompt into query scopes for dynamic output budgeting:
        - 'broad_overview': Multi-section informational overviews, concept breakdowns, complete feature/type explanations.
        - 'code': Code snippets, scripts, implementations.
        - 'reasoning': Algorithmic analysis, formal proofs, step-by-step logic.
        - 'recall': Exact previous turn recall or strict verbatim requests.
        - 'standard_technical': Specific technical concept or syntax questions.
        - 'simple_factual': Short queries, arithmetic, greetings.
        """
        lower = prompt.lower().strip()

        # 1. Exact recall
        recall_markers = [
            "reply with only", "exact text", "exact word", "what exact", "recall previous",
            "repeat exactly", "what was the exact", "what did you reply", "reply with",
            "earlier", "previous message", "last message", "what did i say", "what did you say"
        ]
        if any(m in lower for m in recall_markers):
            return "recall"

        # 2. Code generation
        code_markers = ["def ", "class ", "import ", "function(", "const ", "SELECT ", "curl ", "npm ", "```"]
        if any(marker in prompt for marker in code_markers) or "write a script" in lower or "write code" in lower or "implement a function" in lower:
            return "code"

        # 3. Reasoning
        reasoning_markers = [
            "prove", "analyze complexity", "architect", "deep analysis",
            "step by step", "algorithm", "derive", "calculate", "solve",
            "why does", "explain why", "deduce", "logic", "troubleshoot",
            "root cause", "system design"
        ]
        if any(w in lower for w in reasoning_markers):
            return "reasoning"

        # 4. Broad Overview
        broad_overview_patterns = [
            r"\bwhat\s+is\s+(python|java|c\+\+|rust|go|javascript|typescript|machine\s+learning|oop|sql)\b",
            r"\bexplain\s+(python|java|c\+\+|rust|go|machine\s+learning|oop|sql\s+joins?)\b",
            r"\bexplain\s+[\w\s]+\s+and\s+its\s+(features|types|concepts|architecture|pillars)\b",
            r"\b(what\s+are\s+the\s+types\s+of|types\s+of)\s+inheritance\b",
            r"\bexplain\s+(oop\s+concepts|sql\s+joins?|machine\s+learning)\b",
            r"\b(overview\s+of|architecture\s+of|features\s+of)\s+\w+\b",
            r"\b(in\s+detail|complete\s+overview|all\s+major\s+features|give\s+me\s+the\s+full\s+explanation|comprehensively|deep\s+dive)\b"
        ]
        for pat in broad_overview_patterns:
            if re.search(pat, lower):
                return "broad_overview"

        # Follow-up questions about an active topic
        if active_topic:
            follow_up_broad = [
                r"\b(what\s+are\s+its\s+types|its\s+types\s+and\s+features|all\s+its\s+types|types\s+of\s+it)\b",
                r"\bexplain\s+its\s+(types|features|components)\b",
                r"\bshow\s+all\s+(types|features|examples)\b"
            ]
            for pat in follow_up_broad:
                if re.search(pat, lower):
                    return "broad_overview"

        # 5. Standard Technical
        if self.classify_technical_intent(prompt, active_topic=active_topic):
            return "standard_technical"

        # 6. Simple factual / short chat
        simple_math_or_greeting = [
            r"^\d+\s*[\+\-\*\/]\s*\d+\s*\??$",
            r"^what\s+is\s+\d+\s*[\+\-\*\/]\s*\d+\s*\??$",
            r"^(hello|hi|hey|good\s+morning|good\s+evening|who\s+are\s+you|help)\b"
        ]
        if any(re.search(pat, lower) for pat in simple_math_or_greeting) or len(lower) < 25:
            return "simple_factual"

        return "standard_technical" if len(lower) > 200 else "simple_factual"

    async def resolve_route(
        self,
        prompt: str,
        channel: str = "text",
        override_model: Optional[str] = None,
        has_history: bool = False,
        active_topic: Optional[str] = None
    ) -> RouteResult:
        t0 = time.perf_counter()
        available = await self.get_available_models()
        scope = self.classify_query_scope(prompt, active_topic=active_topic)

        # 1. Explicit UI or API override_model goes through the exact same residency & context gate
        if override_model and override_model != "auto":
            if "nemotron" in override_model.lower() or override_model.startswith("nvidia/"):
                ultra_cfg = self.slots["ultra"]
                pred = (
                    self.output_budgets.get("broad_overview", 1536)
                    if scope == "broad_overview"
                    else ultra_cfg.get("predict", 2048)
                )
                res = await self._admit_and_resolve_route(
                    target_model=override_model,
                    num_ctx=ultra_cfg["ctx"],
                    temperature=ultra_cfg["temp"],
                    pinned=False,
                    keep_alive=ultra_cfg["keep_alive"],
                    reasoning_mode=True,
                    available=available,
                    channel=channel,
                    num_predict=pred,
                    num_thread=ultra_cfg.get("threads", 4),
                    num_batch=ultra_cfg.get("batch", 512),
                    query_scope=scope
                )
            else:
                base_override = override_model[:-7] if override_model.endswith(":latest") else override_model
                profile = self.model_ctx_profiles.get(
                    base_override,
                    {"ctx": 4096, "temp": 0.5, "pinned": False, "keep_alive": "10m", "reasoning": False}
                )
                effective_ctx = self.slots["voice"]["ctx"] if channel == "voice" and profile["pinned"] else profile["ctx"]
                is_heavy = "30b" in base_override or "14b" in base_override
                if scope == "broad_overview":
                    pred_tokens = min(self.output_budgets.get("broad_overview", 1536), max(256, effective_ctx - 512))
                elif is_heavy:
                    pred_tokens = 1024
                elif scope == "recall":
                    pred_tokens = 128
                else:
                    pred_tokens = 512
                res = await self._admit_and_resolve_route(
                    target_model=override_model,
                    num_ctx=effective_ctx,
                    temperature=profile["temp"],
                    pinned=profile["pinned"],
                    keep_alive=profile["keep_alive"],
                    reasoning_mode=profile["reasoning"],
                    available=available,
                    channel=channel,
                    num_predict=pred_tokens,
                    num_thread=4,
                    num_batch=512,
                    query_scope=scope
                )
            logger.debug(f"route.resolved model={res.model} ctx={res.num_ctx} scope={scope} latency_ms={(time.perf_counter()-t0)*1000:.2f}")
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
                channel=channel,
                num_predict=cfg.get("predict", 96),
                num_thread=cfg.get("threads", 4),
                num_batch=cfg.get("batch", 512),
                query_scope="voice"
            )
            return res

        # 3. Structural intent detection for coding
        code_markers = ["def ", "class ", "import ", "function(", "const ", "SELECT ", "curl ", "npm ", "```"]
        if scope == "code" or any(marker in prompt for marker in code_markers) or "write a script" in prompt.lower() or "write code" in prompt.lower():
            cfg = self.slots["code"]
            pred = self.output_budgets.get("code_generation", 1024)
            return await self._admit_and_resolve_route(
                target_model=cfg["model"],
                num_ctx=cfg["ctx"],
                temperature=cfg["temp"],
                pinned=False,
                keep_alive=cfg["keep_alive"],
                reasoning_mode=False,
                available=available,
                channel=channel,
                num_predict=pred,
                num_thread=cfg.get("threads", 6),
                num_batch=cfg.get("batch", 512),
                query_scope="code"
            )

        # 4. Technical concept and programming specification routing (qwen2.5:1.5b)
        if scope in ("broad_overview", "standard_technical") or self.classify_technical_intent(prompt, active_topic=active_topic):
            cfg = self.slots.get("technical", self.slots.get("chat_moderate", {
                "model": "qwen2.5:1.5b", "ctx": 4096, "temp": 0.4, "pinned": True, "keep_alive": -1, "predict": 512
            }))
            if scope == "broad_overview":
                pred = self.output_budgets.get("broad_overview", 1536)
            else:
                pred = self.output_budgets.get("standard_technical", 768)
            # Bound prediction tokens by context headroom: leave at least 512 tokens for prompt & history
            max_headroom = max(128, cfg["ctx"] - 512)
            pred = min(pred, max_headroom)
            return await self._admit_and_resolve_route(
                target_model=cfg["model"],
                num_ctx=cfg["ctx"],
                temperature=cfg["temp"],
                pinned=cfg.get("pinned", True),
                keep_alive=cfg.get("keep_alive", -1),
                reasoning_mode=False,
                available=available,
                channel=channel,
                num_predict=pred,
                num_thread=cfg.get("threads", 4),
                num_batch=cfg.get("batch", 512),
                query_scope=scope
            )

        # 5. Moderate conversational tasks (P0: ONLY when genuinely complex/analytical and long)
        lower_p = prompt.lower()
        analytical_complex_markers = [
            "compare in detail", "synthesize", "comprehensive analysis",
            "technical breakdown", "in-depth explanation"
        ]
        is_genuinely_complex = (
            len(prompt.strip()) > 300
            or any(m in lower_p for m in analytical_complex_markers)
        )
        if is_genuinely_complex and "qwen2.5:1.5b" in available:
            cfg = self.slots.get("chat_moderate", {"model": "qwen2.5:1.5b", "ctx": 4096, "temp": 0.4, "pinned": True, "keep_alive": -1})
            return await self._admit_and_resolve_route(
                target_model=cfg["model"],
                num_ctx=cfg["ctx"],
                temperature=cfg["temp"],
                pinned=True,
                keep_alive=-1,
                reasoning_mode=False,
                available=available,
                channel=channel,
                num_predict=cfg.get("predict", 256),
                num_thread=cfg.get("threads", 4),
                num_batch=cfg.get("batch", 512),
                query_scope=scope
            )

        # 6. Algorithmic reasoning and problem solving detection
        reasoning_markers = [
            "prove", "analyze complexity", "architect", "deep analysis",
            "step by step", "algorithm", "derive", "calculate", "solve",
            "why does", "explain why", "deduce", "logic", "troubleshoot",
            "root cause", "system design"
        ]
        if scope == "reasoning" or any(w in lower_p for w in reasoning_markers):
            cfg = self.slots["reasoning"]
            pred = self.output_budgets.get("reasoning_deep", 1536)
            return await self._admit_and_resolve_route(
                target_model=cfg["model"],
                num_ctx=cfg["ctx"],
                temperature=cfg["temp"],
                pinned=False,
                keep_alive=cfg["keep_alive"],
                reasoning_mode=True,
                available=available,
                channel=channel,
                num_predict=pred,
                num_thread=cfg.get("threads", 6),
                num_batch=cfg.get("batch", 512),
                query_scope="reasoning"
            )

        # 7. Default fast chat & recall route (qwen2.5:0.5b)
        # Note: Short prompts, recall questions, and multi-turn exchanges stay here
        # with full conversation history preserved in the context window.
        cfg = self.slots["chat"]
        if scope == "recall" or len(prompt.strip()) < 30:
            pred = 128
        else:
            pred = self.output_budgets.get("simple_factual", 512)
        return await self._admit_and_resolve_route(
            target_model=cfg["model"],
            num_ctx=cfg["ctx"],
            temperature=cfg["temp"],
            pinned=True,
            keep_alive=-1,
            reasoning_mode=False,
            available=available,
            channel=channel,
            num_predict=pred,
            num_thread=cfg.get("threads", 4),
            num_batch=cfg.get("batch", 512),
            query_scope=scope
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
            gen_url = "/api/generate" if client.base_url.scheme else f"{self.ollama_host}/api/generate"

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
