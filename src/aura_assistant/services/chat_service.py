"""
Aura Assistant - Chat Orchestration Service
Coordinates multi-model routing, streaming LLM token delivery, tool invocation,
diff-only profile caching, non-blocking background persistence, async SSRF-safe web grounding,
and structured stage latency telemetry.
"""

import asyncio
import hashlib
import ipaddress
import json
import logging
import os
import re
import socket
import time
import uuid
from urllib.parse import urlparse, urljoin
import httpx
from typing import AsyncGenerator, Dict, Any, List, Optional, Set, Callable, Tuple

from aura_assistant.core.llm.router import LLMRouter, RouteResult
from aura_assistant.core.llm.provider import OllamaProvider
from aura_assistant.core.tools.registry import ToolRegistry
from aura_assistant.core.memory.episodic import EpisodicMemoryManager
from aura_assistant.core.context.context_engine import ContextEngine
from aura_assistant.core.voice.formatter import VoiceFormatter
from aura_assistant.core.db.session import persist_conversation_turn

logger = logging.getLogger("aura-chat-service")


def _is_ip_globally_safe(ip_str: str) -> bool:
    try:
        ip_obj = ipaddress.ip_address(ip_str)
        if (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_multicast
            or ip_obj.is_reserved
            or ip_obj.is_unspecified
        ):
            return False
        return True
    except Exception:
        return False


def is_safe_external_url(url: str) -> bool:
    """
    Synchronous SSRF validator: verifies HTTP/HTTPS scheme and ensures all resolved
    IPv4/IPv6 addresses are globally routable public addresses.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = (parsed.hostname or "").strip().lower()
        if not hostname or hostname in ("localhost", "0.0.0.0", "::1"):
            return False

        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        addr_info = socket.getaddrinfo(hostname, port)
        if not addr_info:
            return False
        for item in addr_info:
            ip_str = item[4][0]
            if not _is_ip_globally_safe(ip_str):
                return False
        return True
    except Exception:
        return False


async def async_is_safe_external_url(url: str) -> bool:
    """
    Async non-blocking SSRF validator: resolves DNS via loop.getaddrinfo off the event loop
    and rejects loopback, RFC1918 private, link-local (169.254.169.254), IPv6 local, and multicast IPs.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = (parsed.hostname or "").strip().lower()
        if not hostname or hostname in ("localhost", "0.0.0.0", "::1"):
            return False

        # Fast-reject literal IPs before DNS lookup
        try:
            if not _is_ip_globally_safe(hostname):
                return False
        except Exception:
            pass

        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        loop = asyncio.get_running_loop()
        addr_info = await asyncio.wait_for(loop.getaddrinfo(hostname, port), timeout=2.5)
        if not addr_info:
            return False
        for item in addr_info:
            ip_str = item[4][0]
            if not _is_ip_globally_safe(ip_str):
                return False
        return True
    except Exception:
        return False


async def fetch_external_url_safely(
    target_url: str,
    http_client: Optional[httpx.AsyncClient] = None,
    max_bytes: int = 65536,
    max_redirects: int = 2
) -> str:
    """
    Fetches an external HTTP(S) URL with async SSRF verification on the initial URL
    and every redirect hop, explicit timeouts, and a 64 KB response stream cap.
    """
    current_url = target_url
    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(
        timeout=httpx.Timeout(connect=2.5, read=4.0, write=2.5, pool=2.5)
    )
    try:
        for _ in range(max_redirects + 1):
            if not await async_is_safe_external_url(current_url):
                logger.warning(f"Blocked unsafe URL or redirect target (SSRF guard): {current_url}")
                return ""

            headers = {"User-Agent": "AuraSovereignBot/3.5"}
            async with client.stream(
                "GET",
                current_url,
                headers=headers,
                follow_redirects=False,
                timeout=httpx.Timeout(connect=2.5, read=4.0, write=2.5, pool=2.5)
            ) as resp:
                if resp.status_code in (301, 302, 303, 307, 308):
                    loc_header = resp.headers.get("location")
                    if not loc_header:
                        return ""
                    current_url = urljoin(current_url, loc_header)
                    continue

                if resp.status_code != 200:
                    return ""

                chunks: List[bytes] = []
                bytes_read = 0
                async for chunk_bytes in resp.aiter_bytes():
                    chunks.append(chunk_bytes)
                    bytes_read += len(chunk_bytes)
                    if bytes_read >= max_bytes:
                        break
                raw_html = b"".join(chunks).decode("utf-8", errors="replace")
                clean_text = re.sub(r"<[^>]+>", " ", raw_html)
                clean_text = re.sub(r"\s+", " ", clean_text).strip()
                return f"Public web content from {current_url}:\n{clean_text[:1500]}"
        return ""
    except Exception as ex:
        logger.debug(f"Could not fetch URL {target_url}: {ex}")
        return ""
    finally:
        if owns_client and not client.is_closed:
            await client.aclose()


CONTEXT_CACHE_VERSION = "v3.5.2"

EXPLICIT_STATUS_COMMANDS = frozenset({
    "/status",
    "/health",
    "system status",
    "hardware status",
    "show system status",
    "show hardware status"
})

DIAGNOSTIC_OR_MULTI_PART_MARKERS = (
    "explain", "how", "why", "table", "cache", "history", "context",
    "previous", "earlier", "verify", "audit", "describe", "report",
    "telemetry", " and ", "\n", "?"
)

CONTEXT_DEPENDENT_PROMPT_PATTERNS = re.compile(
    r"\b("
    r"previous|earlier|last|above|prior|before|again|recall|remember|"
    r"reply\s+with|exact|what\s+did|you\s+said|your\s+last|"
    r"my|i|me|mine|our|us|this|that|it|they|them|he|she|his|her|"
    r"here|now|today|current|time|date|location|where|status|telemetry|cache|session"
    r")\b",
    re.IGNORECASE
)


def is_dedicated_status_intent(prompt: str, has_history: bool = False) -> bool:
    """
    Matches only a dedicated, standalone status command or single-intent status request.
    Never matches multi-part diagnostic prompts, questions containing 'telemetry',
    or follow-up conversational turns (P0-1).
    """
    raw = (prompt or "").strip()
    if not raw or "\n" in raw or len(raw) > 48:
        return False
    lower = raw.lower()
    if lower in ("/status", "/health"):
        return True
    if has_history:
        return False
    if any(marker in lower for marker in DIAGNOSTIC_OR_MULTI_PART_MARKERS):
        return False
    normalized = re.sub(r"[\.!]+$", "", lower).strip()
    return normalized in EXPLICIT_STATUS_COMMANDS


def _redact_debug_preview(text: str, max_len: int = 80) -> str:
    """Redacts emails, bearer tokens, and long strings for local opt-in trace previews."""
    cleaned = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[REDACTED_EMAIL]", text or "")
    cleaned = re.sub(r"\b(aura_sec_\w+|nvapi-\w+|ghp_\w+)\b", "[REDACTED_TOKEN]", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > max_len:
        return cleaned[:max_len] + "...[REDACTED]"
    return cleaned


class ResponseCache:
    """
    Context-isolated LRU Response Cache for deterministic, stateless queries (P0-3).
    Disables caching by default for multi-turn/follow-up questions and context-dependent prompts.
    Includes a SHA-256 hash of all relevant inputs (session, model, num_ctx, history, memory,
    profile, location, and context_version) and emits explicit cache_hit / cache_miss / cache_bypass reasons.
    """
    def __init__(self, ttl_seconds: int = 300, max_entries: int = 128):
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self._cache: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def evaluate_cacheability(
        prompt: str,
        has_history: bool = False,
        url_context: str = "",
        tool_invoked: bool = False
    ) -> Tuple[bool, str]:
        clean = (prompt or "").strip()
        if not clean:
            return False, "empty_prompt"
        if has_history:
            return False, "multi_turn_history_present"
        if tool_invoked or url_context:
            return False, "dynamic_external_or_tool_context"
        if "\n" in clean or len(clean) > 160:
            return False, "multi_part_or_long_prompt"
        if CONTEXT_DEPENDENT_PROMPT_PATTERNS.search(clean):
            return False, "context_dependent_or_personal_prompt"
        return True, "deterministic_stateless_eligible"

    @staticmethod
    def compute_cache_key(
        prompt: str,
        session_id: str = "default_session",
        model: str = "qwen2.5:0.5b",
        num_ctx: int = 2048,
        history_messages: Optional[List[Dict[str, str]]] = None,
        memory_facts: Optional[List[str]] = None,
        profile_data: Optional[Dict[str, Any]] = None,
        location_key: str = "",
        context_version: str = CONTEXT_CACHE_VERSION
    ) -> str:
        payload = {
            "v": context_version,
            "prompt": (prompt or "").strip().lower(),
            "model": model,
            "num_ctx": int(num_ctx),
            "history": history_messages or [],
            "memory_facts": list(memory_facts or []),
            "profile": dict(sorted((profile_data or {}).items())),
            "location": location_key
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        return f"ctx_cache::{digest}"

    def lookup(
        self,
        prompt: str,
        session_id: str = "default_session",
        model: str = "qwen2.5:0.5b",
        num_ctx: int = 2048,
        history_messages: Optional[List[Dict[str, str]]] = None,
        memory_facts: Optional[List[str]] = None,
        profile_data: Optional[Dict[str, Any]] = None,
        location_key: str = "",
        url_context: str = "",
        tool_invoked: bool = False
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        has_history = bool(history_messages)
        eligible, reason = self.evaluate_cacheability(
            prompt=prompt,
            has_history=has_history,
            url_context=url_context,
            tool_invoked=tool_invoked
        )
        if not eligible:
            return None, {
                "type": "cache_bypass",
                "status": "cache_bypass",
                "reason": reason,
                "cache_key": None
            }

        key = self.compute_cache_key(
            prompt=prompt,
            session_id=session_id,
            model=model,
            num_ctx=num_ctx,
            history_messages=history_messages,
            memory_facts=memory_facts,
            profile_data=profile_data,
            location_key=location_key
        )
        entry = self._cache.get(key)
        if entry:
            if time.time() - entry["timestamp"] < self.ttl:
                return entry["response"], {
                    "type": "cache_hit",
                    "status": "cache_hit",
                    "reason": "deterministic_exact_context_match",
                    "cache_tier": "lru_deterministic_context_hash",
                    "cache_key": key[:24]
                }
            del self._cache[key]

        return None, {
            "type": "cache_miss",
            "status": "cache_miss",
            "reason": "cold_deterministic_key",
            "cache_key": key[:24]
        }

    def store(
        self,
        prompt: str,
        response: str,
        session_id: str = "default_session",
        model: str = "qwen2.5:0.5b",
        num_ctx: int = 2048,
        history_messages: Optional[List[Dict[str, str]]] = None,
        memory_facts: Optional[List[str]] = None,
        profile_data: Optional[Dict[str, Any]] = None,
        location_key: str = "",
        url_context: str = "",
        tool_invoked: bool = False
    ) -> bool:
        if not response or len(response.strip()) <= 5:
            return False
        eligible, _ = self.evaluate_cacheability(
            prompt=prompt,
            has_history=bool(history_messages),
            url_context=url_context,
            tool_invoked=tool_invoked
        )
        if not eligible:
            return False

        if len(self._cache) >= self.max_entries:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k]["timestamp"])
            del self._cache[oldest_key]

        key = self.compute_cache_key(
            prompt=prompt,
            session_id=session_id,
            model=model,
            num_ctx=num_ctx,
            history_messages=history_messages,
            memory_facts=memory_facts,
            profile_data=profile_data,
            location_key=location_key
        )
        self._cache[key] = {
            "response": response,
            "timestamp": time.time(),
            "model": model,
            "session_id": session_id
        }
        return True

    def get(self, prompt: str, location_key: str = "", **kwargs) -> Optional[str]:
        val, _ = self.lookup(prompt=prompt, location_key=location_key, **kwargs)
        return val

    def set(self, prompt: str, response: str, location_key: str = "", **kwargs) -> bool:
        return self.store(prompt=prompt, response=response, location_key=location_key, **kwargs)


class ChatService:
    def __init__(
        self,
        router: LLMRouter,
        provider: OllamaProvider,
        tools: ToolRegistry,
        memory: EpisodicMemoryManager,
        context_engine: Optional[ContextEngine] = None,
        max_bg_concurrency: int = 8
    ):
        self.router = router
        self.provider = provider
        self.tools = tools
        self.memory = memory
        self.context_engine = context_engine or ContextEngine()
        self.response_cache = ResponseCache()
        self._bg_semaphore = asyncio.Semaphore(max_bg_concurrency)
        self._bg_tasks: Set[asyncio.Task] = set()
        self._session_locks: Dict[str, asyncio.Lock] = {}
        self.last_pre_inference_trace: Dict[str, Any] = {}

    def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        lock = self._session_locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._session_locks[session_id] = lock
        return lock

    def _enqueue_background_io(self, sync_fn: Callable[[], None]) -> None:
        """Schedules a synchronous disk/SQLite function off the event loop in a tracked bounded task."""
        async def _runner():
            async with self._bg_semaphore:
                try:
                    await asyncio.to_thread(sync_fn)
                except Exception as e:
                    logger.error(f"Background persistence worker error: {e}")

        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(_runner())
            self._bg_tasks.add(task)
            task.add_done_callback(self._bg_tasks.discard)
        except RuntimeError:
            sync_fn()

    async def flush_background_tasks(self) -> None:
        """Awaits completion of all queued background persistence tasks."""
        if self._bg_tasks:
            await asyncio.gather(*list(self._bg_tasks), return_exceptions=True)

    async def shutdown(self) -> None:
        """Drains pending persistence tasks cleanly during application shutdown."""
        await self.flush_background_tasks()

    def _build_measured_status_fast_path(self, route: RouteResult) -> str:
        """
        Builds a deterministic status response reporting ONLY properties actually measured
        in the current runtime (never claiming unmeasured air-gap or model execution).
        """
        daemon_state = "offline_simulation" if self.provider.is_offline_simulation else "online"
        vram_info = ""
        if getattr(self.router, "vram_arbiter", None) is not None:
            tel = self.router.vram_arbiter.get_telemetry()
            vram_info = (
                f" VRAM used={tel.get('used_mb', 0)}/{tel.get('ceiling_mb', 0)} MiB "
                f"(loaded={tel.get('loaded_models', [])})."
            )
        return (
            f"[Deterministic Status Fast Path] Ollama daemon={daemon_state}. "
            f"Selected route model={route.model} (configured num_ctx={route.num_ctx:,} tokens).{vram_info}"
        )

    async def handle_message_stream(
        self,
        prompt: str,
        channel: str = "text",
        speaker_verified: bool = True,
        biometric_score: float = 1.0,
        override_model: Optional[str] = None,
        location: Optional[Dict[str, Any]] = None,
        session_id: str = "default_session",
        request_id: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        req_id = request_id or f"req_{uuid.uuid4().hex[:12]}"
        session_lock = self._get_session_lock(session_id)

        async with session_lock:
            t_req_start = time.perf_counter()

            # Reconcile session history from durable SQLite store before routing/context assembly (P1-6)
            prior_turns = await asyncio.to_thread(
                self.context_engine.get_or_create_history,
                session_id,
                True
            )
            has_history = len(prior_turns) > 0

            # 1. Multi-Model Intent & Residency Resolution (P2-8: passes has_history)
            t0 = time.perf_counter()
            route: RouteResult = await self.router.resolve_route(
                prompt=prompt,
                channel=channel,
                override_model=override_model,
                has_history=has_history
            )
            route_ms = (time.perf_counter() - t0) * 1000.0

            yield {
                "type": "routing",
                "request_id": req_id,
                "model": route.model,
                "pinned": route.pinned,
                "num_ctx": route.num_ctx,
                "keep_alive": route.keep_alive,
                "fallback_reason": route.fallback_reason,
                "channel": channel
            }

            # 2. Diff-Only Location Context Update
            pending_orm_entries: List[Dict[str, Any]] = []
            profile_needs_write = False
            if location:
                lat = location.get("latitude")
                lon = location.get("longitude")
                city = location.get("city") or location.get("locality") or "Unknown"
                country = location.get("country") or "India"
                region = location.get("region") or location.get("principalSubdivision") or ""
                tz = location.get("timezone") or "Asia/Kolkata"

                loc_summary = f"{city}, {region}, {country}".strip(", ")
                loc_updates: Dict[str, Any] = {
                    "location": loc_summary,
                    "timezone": tz
                }
                if lat is not None and lon is not None:
                    loc_updates["coordinates"] = f"{lat}, {lon}"

                changed, loc_orm = self.memory.update_profile_facts(loc_updates, persist_sync=False)
                if changed:
                    profile_needs_write = True
                    pending_orm_entries.extend(loc_orm)

            # 3. URL and Profile Detection (with non-blocking async SSRF defense & redirect revalidation)
            url_context = ""
            if "```" not in prompt:
                url_match = re.search(r"https?://[^\s]+", prompt)
                if url_match:
                    target_url = url_match.group(0).rstrip(".,;)")
                    if "linkedin.com" in target_url:
                        slug_match = re.search(r"linkedin\.com/in/([^/?#]+)", target_url)
                        name_guess = ""
                        if slug_match:
                            raw_slug = slug_match.group(1)
                            cleaned = re.sub(r"-[a-zA-Z0-9]+$", "", raw_slug).replace("-", " ").title()
                            name_guess = cleaned.strip()

                        li_updates: Dict[str, Any] = {"linkedin_url": target_url}
                        if name_guess:
                            li_updates["name"] = name_guess
                        li_changed, li_orm = self.memory.update_profile_facts(li_updates, persist_sync=False)
                        if li_changed:
                            profile_needs_write = True
                            pending_orm_entries.extend(li_orm)

                        url_context = (
                            f"The user provided their LinkedIn profile: {target_url} (Identified Name: '{name_guess or 'User'}').\n"
                            f"LinkedIn blocks unauthenticated scrapers. Confirm receipt of their link and explain that their profile "
                            f"identity '{name_guess}' has been safely registered in sovereign local memory."
                        )
                    else:
                        shared_client = self.provider._get_client()
                        url_context = await fetch_external_url_safely(target_url, http_client=shared_client)

            # 4. Conversational Tool Dispatch (when prompt explicitly invokes a registered tool)
            tool_invoked = False
            tool_match = re.search(r"\[TOOL:\s*(\w+)\s*(\{.*?\})\]", prompt)
            if tool_match:
                tool_invoked = True
                tool_name = tool_match.group(1)
                try:
                    tool_args = json.loads(tool_match.group(2))
                except Exception:
                    tool_args = {}
                tool_result = await self.tools.execute_tool(
                    name=tool_name,
                    params=tool_args,
                    speaker_verified=speaker_verified,
                    biometric_score=biometric_score,
                    channel=channel
                )
                yield {"type": "tool_result", "tool": tool_name, "result": tool_result}
                url_context = (url_context + f"\nTool '{tool_name}' Output: {json.dumps(tool_result)}").strip()

            # 5. Context Engineering Architecture (protects latest exchange before optional layers)
            t_ctx0 = time.perf_counter()
            profile_data = self.memory.get_profile()
            resolved_query = self.context_engine.resolve_coreferences(session_id, prompt)
            relevant_facts = self.memory.retrieve_relevant_facts(resolved_query, limit=4)

            messages, context_telemetry = self.context_engine.build_engineered_context(
                session_id=session_id,
                current_prompt=prompt,
                location=location,
                profile_data=profile_data,
                memory_facts=relevant_facts,
                url_context=url_context,
                reasoning_mode=route.reasoning_mode,
                max_ctx_override=route.num_ctx,
                sync_from_db=False
            )
            ctx_ms = (time.perf_counter() - t_ctx0) * 1000.0
            pre_llm_overhead_ms = (time.perf_counter() - t_req_start) * 1000.0
            context_telemetry["request_id"] = req_id
            context_telemetry["pre_llm_overhead_ms"] = round(pre_llm_overhead_ms, 2)
            context_telemetry["route_resolution_ms"] = round(route_ms, 2)
            context_telemetry["context_assembly_ms"] = round(ctx_ms, 2)

            yield {
                "type": "context_telemetry",
                "context": context_telemetry
            }

            # 6. Dedicated Status Intent Check (P0-1) & Context-Isolated Response Cache Check (P0-3)
            location_key = f"{location.get('city', '')},{location.get('country', '')}" if location else ""
            history_slice = messages[1:-1] if len(messages) > 2 else []

            fast_path_text: Optional[str] = None
            response_source: str = "live_model"

            if is_dedicated_status_intent(prompt, has_history=has_history):
                fast_path_text = self._build_measured_status_fast_path(route)
                response_source = "deterministic_fast_path"
                cache_event = {
                    "type": "cache_bypass",
                    "status": "cache_bypass",
                    "reason": "dedicated_status_fast_path",
                    "cache_key": None
                }
                yield cache_event
            else:
                cached_response, cache_event = self.response_cache.lookup(
                    prompt=prompt,
                    session_id=session_id,
                    model=route.model,
                    num_ctx=route.num_ctx,
                    history_messages=history_slice,
                    memory_facts=relevant_facts,
                    profile_data=profile_data,
                    location_key=location_key,
                    url_context=url_context,
                    tool_invoked=tool_invoked
                )
                yield cache_event
                if cached_response is not None:
                    fast_path_text = cached_response
                    response_source = "response_cache"

            # 7. Structured Pre-Inference Diagnostics (P1-4)
            pre_inference_diagnostics: Dict[str, Any] = {
                "request_id": req_id,
                "session_id": session_id,
                "routed_model": route.model,
                "effective_num_ctx": route.num_ctx,
                "ordered_message_roles": [m.get("role", "unknown") for m in messages],
                "previous_exchange_present": bool(context_telemetry.get("previous_exchange_present", False)),
                "estimated_tokens": {
                    "system": context_telemetry.get("estimated_system_tokens", 0),
                    "history": context_telemetry.get("estimated_history_tokens", 0),
                    "user": context_telemetry.get("estimated_user_tokens", 0),
                    "total": context_telemetry.get("estimated_total_tokens", 0),
                    "is_exact_model_count": False
                },
                "history_selection_decision": {
                    "turns_included": context_telemetry.get("history_turns_included", 0),
                    "turns_skipped": context_telemetry.get("history_turns_skipped", 0),
                    "latest_exchange_protected": context_telemetry.get("latest_exchange_protected", False),
                    "trim_reasons": context_telemetry.get("trim_reasons", [])
                },
                "cache_status": cache_event["status"],
                "cache_reason": cache_event["reason"],
                "response_source": response_source
            }
            if os.environ.get("AURA_DEBUG_TRACE") == "1":
                pre_inference_diagnostics["redacted_message_previews"] = [
                    {"role": m.get("role", ""), "preview": _redact_debug_preview(m.get("content", ""))}
                    for m in messages
                ]

            self.last_pre_inference_trace = pre_inference_diagnostics
            logger.info(f"chat.pre_inference_trace {json.dumps(pre_inference_diagnostics)}")

            full_response_acc: List[str] = []

            if fast_path_text is not None:
                words = fast_path_text.split(" ")
                for i, word in enumerate(words):
                    token = word + (" " if i < len(words) - 1 else "")
                    full_response_acc.append(token)
                    yield {"type": "token", "content": token}
                    if i % 3 == 2:
                        await asyncio.sleep(0.001)
            else:
                async for token in self.provider.stream_chat(
                    model=route.model,
                    messages=messages,
                    temperature=route.temperature,
                    num_ctx=route.num_ctx,
                    keep_alive=route.keep_alive
                ):
                    full_response_acc.append(token)
                    yield {"type": "token", "content": token}
                response_source = getattr(self.provider, "last_response_source", "live_model")
                pre_inference_diagnostics["response_source"] = response_source

            complete_text = "".join(full_response_acc)

            # Only store in response cache if generated by live_model and eligible (P0-3)
            if response_source == "live_model" and complete_text and len(complete_text) > 5:
                self.response_cache.store(
                    prompt=prompt,
                    response=complete_text,
                    session_id=session_id,
                    model=route.model,
                    num_ctx=route.num_ctx,
                    history_messages=history_slice,
                    memory_facts=relevant_facts,
                    profile_data=profile_data,
                    location_key=location_key,
                    url_context=url_context,
                    tool_invoked=tool_invoked
                )

            # 8. Durable Turn Persistence (P1-6: read-after-write consistency across requests & workers)
            compacted_chunk = await asyncio.to_thread(
                self.context_engine.record_turn,
                session_id,
                prompt,
                complete_text,
                route.model,
                req_id
            )
            if compacted_chunk:
                arch_orm = self.memory.archive_compacted_summary(session_id, compacted_chunk, persist_sync=False)
                if arch_orm:
                    pending_orm_entries.append(arch_orm)

            extracted_orm = await self.memory.extract_facts_from_turn(prompt, complete_text, persist_sync=False)
            if extracted_orm:
                pending_orm_entries.extend(extracted_orm)
                if any(e.get("kind") == "profile" for e in extracted_orm):
                    profile_needs_write = True

            if pending_orm_entries or profile_needs_write:
                self._enqueue_background_io(
                    lambda: self.memory.flush_persistence_sync(pending_orm_entries, write_profile=profile_needs_write)
                )

            # 9. Spoken output generation if voice channel
            if channel == "voice":
                spoken_text = VoiceFormatter.format_for_speech(complete_text)
                sentences = VoiceFormatter.split_into_sentences(spoken_text)
                yield {
                    "type": "voice_sentences",
                    "sentences": sentences
                }

            yield {
                "type": "pre_inference_trace",
                "trace": pre_inference_diagnostics
            }

            # 10. Emit 'done' with explicit response_source and cache telemetry (P1-7)
            yield {
                "type": "done",
                "request_id": req_id,
                "complete_text": complete_text,
                "model": route.model,
                "response_source": response_source,
                "cache_status": cache_event["status"],
                "cache_reason": cache_event["reason"],
                "previous_exchange_present": pre_inference_diagnostics["previous_exchange_present"],
                "pre_llm_overhead_ms": round(pre_llm_overhead_ms, 2)
            }
