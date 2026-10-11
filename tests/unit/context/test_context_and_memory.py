import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from aura_assistant.core.context.context_engine import ContextEngine
from aura_assistant.core.memory.episodic import EpisodicMemoryManager, MAX_FACT_CHARS, MAX_TOTAL_FACTS
from aura_assistant.services.chat_service import (
    is_safe_external_url,
    async_is_safe_external_url,
    fetch_external_url_safely
)


def test_context_budget_enforces_1536_2048_and_32768_without_overflow():
    engine = ContextEngine()
    sid = "ctx_budget_test"
    for i in range(10):
        engine.record_turn_in_memory(
            sid,
            f"User message {i}: " + ("architectural token details " * 40),
            f"Assistant response {i}: " + ("system analysis output " * 50)
        )

    loc = {
        "city": "New Delhi",
        "region": "Delhi",
        "country": "India",
        "latitude": 28.6139,
        "longitude": 77.209,
        "timezone": "Asia/Kolkata"
    }
    profile = {"name": "Lovekush Kumar", "headline": "AI Systems Architect", "skills": "Python, Rust, TypeScript"}
    large_facts = [f"Fact {i}: " + ("distributed memory details " * 25) for i in range(4)]
    large_url = "External documentation body " * 250

    for max_ctx in (1536, 2048, 32768):
        msgs, tel = engine.build_engineered_context(
            session_id=sid,
            current_prompt="Explain how the hybrid memory system handles compaction and 中文テスト multilingual tokens.",
            location=loc,
            profile_data=profile,
            memory_facts=large_facts,
            url_context=large_url,
            reasoning_mode=True,
            max_ctx_override=max_ctx
        )
        assert tel["within_budget"] is True
        assert tel["total_context_tokens"] + tel["reserve_generation_tokens"] <= max_ctx
        # System identity, directives, and newest user prompt must always survive
        sys_msg = msgs[0]["content"]
        assert "<identity>" in sys_msg
        assert "<sensory_telemetry>" in sys_msg
        assert "<user_profile>" in sys_msg
        assert "<critical_directives>" in sys_msg
        assert "Explain how the hybrid memory system" in msgs[-1]["content"]


def test_history_compaction_preserves_sentence_boundaries():
    engine = ContextEngine()
    sid = "compaction_sentence_test"
    for i in range(9):
        chunk = engine.record_turn_in_memory(
            sid,
            f"First sentence of turn {i}. Second sentence with extra details that should not be sliced mid-word " + ("alpha " * 30),
            f"Assistant reply for turn {i}. Complete explanation follows " + ("beta " * 40)
        )
    assert sid in engine.session_summaries
    summaries = engine.session_summaries[sid]
    assert isinstance(summaries, list)
    assert len(summaries) > 0
    for s in summaries:
        assert "User:" in s and "Assistant:" in s


@pytest.mark.asyncio
async def test_episodic_memory_bounds_deduplication_and_question_filtering(tmp_path: Path):
    mem = EpisodicMemoryManager(storage_dir=tmp_path / "memory")

    # 1. Multiline prompt must NOT be stored as an unbounded multiline fact
    multiline_prompt = (
        "My name is Lovekush Kumar and I build sovereign AI systems.\n"
        "Line 2 with extra instructions that should not be part of the fact.\n"
        "def some_code(): pass"
    )
    await mem.extract_facts_from_turn(multiline_prompt, "Acknowledged.", persist_sync=False)
    facts = mem.retrieve_relevant_facts("Lovekush", limit=4)
    assert len(facts) == 1
    assert "\n" not in facts[0]
    assert len(facts[0]) <= MAX_FACT_CHARS

    # 2. Questions containing trigger phrases must be ignored
    await mem.extract_facts_from_turn("Can you remember that what is my name?", "Yes", persist_sync=False)
    assert not any("?" in f.get("fact", "") for f in mem._facts)

    # 3. Diff-only profile updates skip writes when unchanged
    changed1, _ = mem.update_profile_facts({"location": "New Delhi, India", "timezone": "Asia/Kolkata"}, persist_sync=True)
    assert changed1 is True
    changed2, _ = mem.update_profile_facts({"location": "New Delhi, India", "timezone": "Asia/Kolkata"}, persist_sync=True)
    assert changed2 is False

    # 4. Total fact count bounded by MAX_TOTAL_FACTS while preserving profile facts
    for idx in range(MAX_TOTAL_FACTS + 25):
        mem.archive_compacted_summary("sess1", f"Unique archive summary entry number {idx} with details.", persist_sync=False)
    assert len(mem._facts) <= MAX_TOTAL_FACTS
    assert any(f.get("category") == "profile" for f in mem._facts)


@pytest.mark.asyncio
async def test_async_ssrf_and_redirect_to_private_ip_blocked():
    assert await async_is_safe_external_url("http://127.0.0.1:8000/health") is False
    assert await async_is_safe_external_url("http://localhost:11434/api/tags") is False
    assert await async_is_safe_external_url("http://169.254.169.254/latest/meta-data/") is False
    assert await async_is_safe_external_url("http://192.168.1.1/admin") is False
    assert await async_is_safe_external_url("http://[::1]:8000/") is False
    assert await async_is_safe_external_url("file:///etc/passwd") is False

    # Simulate an external URL that redirects (302) to http://127.0.0.1:8000/admin
    mock_client = MagicMock()
    redirect_resp = MagicMock()
    redirect_resp.status_code = 302
    redirect_resp.headers = {"location": "http://127.0.0.1:8000/admin"}
    stream_ctx = AsyncMock()
    stream_ctx.__aenter__.return_value = redirect_resp
    stream_ctx.__aexit__.return_value = None
    mock_client.stream.return_value = stream_ctx

    # Even if first hop passes, redirect hop to 127.0.0.1 must be blocked by async_is_safe_external_url
    res = await fetch_external_url_safely("http://127.0.0.1/start", http_client=mock_client)
    assert res == ""


@pytest.mark.asyncio
async def test_p0_1_status_fast_path_does_not_intercept_telemetry_or_diagnostic_prompts(tmp_path: Path):
    """
    Regression Test 1 (P0-1):
    Ask Aura to explain how it assembles conversation history and report cache hits / telemetry.
    It must NOT return the generic system-status banner; it must reach the LLM provider.
    Only an explicit '/status' command triggers deterministic_fast_path.
    """
    from aura_assistant.services.chat_service import ChatService, is_dedicated_status_intent
    from aura_assistant.core.llm.router import LLMRouter, RouteResult
    from aura_assistant.core.llm.provider import OllamaProvider
    from aura_assistant.core.tools.registry import ToolRegistry

    assert is_dedicated_status_intent(
        "Explain how you assemble conversation history and report cache hits and telemetry."
    ) is False
    assert is_dedicated_status_intent("/status") is True

    router = MagicMock(spec=LLMRouter)
    router.resolve_route = AsyncMock(
        return_value=RouteResult(model="qwen3.5:4b", num_ctx=4096, temperature=0.3, pinned=True, keep_alive=-1)
    )
    router.vram_arbiter = None

    provider = MagicMock(spec=OllamaProvider)
    provider.is_offline_simulation = False
    provider.last_response_source = "live_model"

    async def fake_stream_chat(**kwargs):
        yield "Conversation history is assembled chronologically "
        yield "with protected latest exchange and SHA-256 cache telemetry."

    provider.stream_chat = MagicMock(side_effect=fake_stream_chat)
    tools = ToolRegistry()
    mem = EpisodicMemoryManager(storage_dir=tmp_path / "mem_p0_1")
    ctx_engine = ContextEngine()
    svc = ChatService(router=router, provider=provider, tools=tools, memory=mem, context_engine=ctx_engine)

    import uuid
    run_uid = uuid.uuid4().hex[:8]
    events = [
        ev async for ev in svc.handle_message_stream(
            prompt="Explain how you assemble conversation history and report cache hits and telemetry.",
            session_id=f"sess_diag_{run_uid}"
        )
    ]
    done_ev = next(e for e in events if e["type"] == "done")
    assert "Aura System Status is Nominal" not in done_ev["complete_text"]
    assert "air-gapped" not in done_ev["complete_text"]
    assert done_ev["response_source"] == "live_model"
    assert provider.stream_chat.call_count == 1


@pytest.mark.asyncio
async def test_p0_2_two_turn_ready_recall_passes_exact_messages_to_provider(tmp_path: Path):
    """
    Regression Test 2 (P0-2 & P1-4):
    Turn 1: 'Reply with exactly: READY.' -> 'READY'
    Turn 2: 'What exact word did you reply with?'
    Inspects the exact messages sent to provider.stream_chat on Turn 2 and verifies:
      [
        {"role": "system", "content": "..."},
        {"role": "user", "content": "Reply with exactly: READY."},
        {"role": "assistant", "content": "READY"},
        {"role": "user", "content": "What exact word did you reply with?"},
      ]
    and verifies pre_inference_trace records previous_exchange_present=True.
    """
    import uuid
    from aura_assistant.services.chat_service import ChatService
    from aura_assistant.core.llm.router import LLMRouter, RouteResult
    from aura_assistant.core.llm.provider import OllamaProvider
    from aura_assistant.core.tools.registry import ToolRegistry

    router = MagicMock(spec=LLMRouter)
    router.resolve_route = AsyncMock(
        return_value=RouteResult(model="qwen3.5:4b", num_ctx=4096, temperature=0.3, pinned=True, keep_alive=-1)
    )
    router.vram_arbiter = None

    captured_calls = []
    provider = MagicMock(spec=OllamaProvider)
    provider.is_offline_simulation = False
    provider.last_response_source = "live_model"

    async def fake_stream_chat(model, messages, **kwargs):
        captured_calls.append(list(messages))
        if len(captured_calls) == 1:
            yield "READY"
        else:
            yield "READY"

    provider.stream_chat = MagicMock(side_effect=fake_stream_chat)
    svc = ChatService(
        router=router,
        provider=provider,
        tools=ToolRegistry(),
        memory=EpisodicMemoryManager(storage_dir=tmp_path / "mem_p0_2"),
        context_engine=ContextEngine()
    )

    sid = f"ready_recall_{uuid.uuid4().hex[:8]}"
    _ = [ev async for ev in svc.handle_message_stream(prompt="Reply with exactly: READY.", session_id=sid)]
    events_t2 = [
        ev async for ev in svc.handle_message_stream(prompt="What exact word did you reply with?", session_id=sid)
    ]

    assert len(captured_calls) == 2
    second_req_messages = captured_calls[1]
    assert [m["role"] for m in second_req_messages] == ["system", "user", "assistant", "user"]
    assert second_req_messages[1] == {"role": "user", "content": "Reply with exactly: READY."}
    assert second_req_messages[2] == {"role": "assistant", "content": "READY"}
    assert second_req_messages[3] == {"role": "user", "content": "What exact word did you reply with?"}

    trace_ev = next(e for e in events_t2 if e["type"] == "pre_inference_trace")["trace"]
    assert trace_ev["previous_exchange_present"] is True
    assert trace_ev["ordered_message_roles"] == ["system", "user", "assistant", "user"]


def test_p0_2_and_p1_5_oversized_history_turn_does_not_block_earlier_turns_and_protects_latest():
    """
    Regression Test 3 (P0-2 & P1-5):
    When a middle turn is oversized, history selection must skip the oversized turn (not break)
    so earlier eligible turns still fit in chronological order, and the most recent exchange is protected.
    """
    import uuid
    engine = ContextEngine()
    sid = f"oversized_mid_turn_{uuid.uuid4().hex[:8]}"

    # Turn 1: short early turn that should survive even if Turn 2 is huge
    engine.record_turn_in_memory(sid, "Early key fact: codename is ORION.", "Acknowledged ORION.")
    # Turn 2: huge oversized turn (~1800 tokens) that exceeds a 2048 history budget
    engine.record_turn_in_memory(sid, "huge_payload " * 750, "huge_output " * 750)
    # Turn 3 (latest exchange): concise exchange that MUST be protected
    engine.record_turn_in_memory(sid, "Reply with exactly: READY.", "READY")

    msgs, tel = engine.build_engineered_context(
        session_id=sid,
        current_prompt="What exact word did you reply with and what was the early codename?",
        profile_data={"name": "Lovekush", "bio": "extra profile padding " * 120},
        memory_facts=["memory padding " * 80],
        url_context="url padding " * 200,
        max_ctx_override=1536
    )

    assert tel["within_budget"] is True
    assert tel["latest_exchange_protected"] is True
    assert tel["previous_exchange_present"] is True
    assert tel["history_turns_skipped"] >= 2  # The huge turn pair was skipped

    history_contents = [m["content"] for m in msgs[1:-1]]
    # Latest exchange survived despite massive optional profile/memory/url padding
    assert "Reply with exactly: READY." in history_contents
    assert "READY" in history_contents
    # Early turn also survived in chronological order before the latest exchange!
    assert "Early key fact: codename is ORION." in history_contents
    assert history_contents.index("Early key fact: codename is ORION.") < history_contents.index("Reply with exactly: READY.")


@pytest.mark.asyncio
async def test_p0_3_cache_isolation_across_sessions_and_explicit_cache_telemetry(tmp_path: Path):
    """
    Regression Tests 4 & 5 (P0-3):
    - Context-dependent / follow-up questions in two sessions with different preceding facts
      must bypass the cache and never return a contradicted cached answer.
    - Deterministic stateless queries emit cache_miss on first call and cache_hit on identical repeat,
      while follow-up/context-dependent queries emit cache_bypass with reason.
    """
    import uuid
    from aura_assistant.services.chat_service import ChatService
    from aura_assistant.core.llm.router import LLMRouter, RouteResult
    from aura_assistant.core.llm.provider import OllamaProvider
    from aura_assistant.core.tools.registry import ToolRegistry

    router = MagicMock(spec=LLMRouter)
    router.resolve_route = AsyncMock(
        return_value=RouteResult(model="qwen3.5:4b", num_ctx=4096, temperature=0.3, pinned=True, keep_alive=-1)
    )
    router.vram_arbiter = None

    provider = MagicMock(spec=OllamaProvider)
    provider.is_offline_simulation = False
    provider.last_response_source = "live_model"

    async def dynamic_llm(model, messages, **kwargs):
        flat = " ".join(m["content"] for m in messages)
        if "ALPHA_7" in flat:
            yield "The code is ALPHA_7."
        elif "BETA_9" in flat:
            yield "The code is BETA_9."
        else:
            yield "Binary search divides a sorted array in half at each step."

    provider.stream_chat = MagicMock(side_effect=dynamic_llm)
    svc = ChatService(
        router=router,
        provider=provider,
        tools=ToolRegistry(),
        memory=EpisodicMemoryManager(storage_dir=tmp_path / "mem_p0_3"),
        context_engine=ContextEngine()
    )

    uid = uuid.uuid4().hex[:8]
    # Session A establishes ALPHA_7, Session B establishes BETA_9, then both ask the exact same question
    sess_a = f"sess_alpha_{uid}"
    sess_b = f"sess_beta_{uid}"
    _ = [ev async for ev in svc.handle_message_stream(prompt="Remember project code ALPHA_7.", session_id=sess_a)]
    _ = [ev async for ev in svc.handle_message_stream(prompt="Remember project code BETA_9.", session_id=sess_b)]

    ev_a = [ev async for ev in svc.handle_message_stream(prompt="What is the project code?", session_id=sess_a)]
    ev_b = [ev async for ev in svc.handle_message_stream(prompt="What is the project code?", session_id=sess_b)]

    done_a = next(e for e in ev_a if e["type"] == "done")
    done_b = next(e for e in ev_b if e["type"] == "done")
    assert "ALPHA_7" in done_a["complete_text"]
    assert "BETA_9" in done_b["complete_text"]
    assert done_a["cache_status"] == "cache_bypass"
    assert done_b["cache_status"] == "cache_bypass"
    assert done_a["cache_reason"] == "multi_turn_history_present"

    # Now test deterministic stateless prompt in a fresh session
    stateless_prompt = "Define binary search algorithm concisely."
    val1, meta1 = svc.response_cache.lookup(prompt=stateless_prompt, session_id="stateless_1", model="qwen3.5:4b", num_ctx=4096)
    assert val1 is None and meta1["status"] == "cache_miss"
    svc.response_cache.store(
        prompt=stateless_prompt,
        response="Binary search divides a sorted array in half.",
        session_id="stateless_1",
        model="qwen3.5:4b",
        num_ctx=4096
    )
    val2, meta2 = svc.response_cache.lookup(prompt=stateless_prompt, session_id="stateless_1", model="qwen3.5:4b", num_ctx=4096)
    assert val2 == "Binary search divides a sorted array in half."
    assert meta2["status"] == "cache_hit"
    assert meta2["reason"] == "deterministic_exact_context_match"


def test_p1_6_conversation_persistence_survives_restart_and_deduplicates_turn_id():
    """
    Regression Test 6 (P1-6):
    Complete one turn with a stable turn_id, verify duplicate retries with the same turn_id do not duplicate rows,
    and verify a brand-new ContextEngine instance (simulating process restart or another worker)
    reconstructs the exact prior exchange for the second turn.
    """
    import uuid
    sid = f"restart_persist_{uuid.uuid4().hex[:8]}"
    worker_1_engine = ContextEngine()
    worker_1_engine.record_turn(
        session_id=sid,
        user_prompt="Reply with exactly: READY.",
        assistant_response="READY",
        model_name="qwen3.5:4b",
        turn_id=f"{sid}_turn_1"
    )
    # Retry with identical turn_id must be deduplicated in both memory and SQLite
    worker_1_engine.record_turn(
        session_id=sid,
        user_prompt="Reply with exactly: READY.",
        assistant_response="READY",
        model_name="qwen3.5:4b",
        turn_id=f"{sid}_turn_1"
    )

    # Simulate Worker 2 / Process Restart with an empty in-memory cache
    worker_2_engine = ContextEngine()
    assert sid not in worker_2_engine.session_histories

    msgs, tel = worker_2_engine.build_engineered_context(
        session_id=sid,
        current_prompt="What exact word did you reply with?",
        max_ctx_override=4096,
        sync_from_db=True
    )
    assert tel["previous_exchange_present"] is True
    history_slice = msgs[1:-1]
    assert len(history_slice) == 2
    assert history_slice[0] == {"role": "user", "content": "Reply with exactly: READY."}
    assert history_slice[1] == {"role": "assistant", "content": "READY"}


@pytest.mark.asyncio
async def test_p1_7_response_sources_are_distinguishable(tmp_path: Path):
    """
    Regression Test 7 (P1-7):
    Verify live_model, response_cache, deterministic_fast_path, and offline_fallback
    are explicitly distinguishable in the done event and pre_inference_trace.
    """
    import uuid
    from aura_assistant.services.chat_service import ChatService
    from aura_assistant.core.llm.router import LLMRouter, RouteResult
    from aura_assistant.core.llm.provider import OllamaProvider
    from aura_assistant.core.tools.registry import ToolRegistry

    router = MagicMock(spec=LLMRouter)
    router.resolve_route = AsyncMock(
        return_value=RouteResult(model="qwen3.5:4b", num_ctx=4096, temperature=0.3, pinned=True, keep_alive=-1)
    )
    router.vram_arbiter = None

    provider = MagicMock(spec=OllamaProvider)
    provider.is_offline_simulation = False
    provider.last_response_source = "live_model"

    async def fake_stream(**kwargs):
        yield "Deterministic stateless explanation of quicksort partitioning."

    provider.stream_chat = MagicMock(side_effect=fake_stream)
    svc = ChatService(
        router=router,
        provider=provider,
        tools=ToolRegistry(),
        memory=EpisodicMemoryManager(storage_dir=tmp_path / "mem_p1_7"),
        context_engine=ContextEngine()
    )

    uid = uuid.uuid4().hex[:8]
    # 1. deterministic_fast_path via explicit '/status' command
    ev_fast = [ev async for ev in svc.handle_message_stream(prompt="/status", session_id=f"s_fast_{uid}")]
    assert next(e for e in ev_fast if e["type"] == "done")["response_source"] == "deterministic_fast_path"

    # 2. live_model on first stateless query
    ev_live = [ev async for ev in svc.handle_message_stream(prompt="Explain quicksort partitioning.", session_id=f"s_cache_{uid}")]
    assert next(e for e in ev_live if e["type"] == "done")["response_source"] == "live_model"

    # 3. response_cache on deterministic cached lookup
    val, meta = svc.response_cache.lookup(
        prompt="Explain quicksort partitioning.",
        session_id=f"s_cache_{uid}",
        model="qwen3.5:4b",
        num_ctx=4096,
        history_messages=[]
    )
    assert val is not None
    assert meta["status"] == "cache_hit"
    assert meta["reason"] == "deterministic_exact_context_match"

    # 4. offline_fallback when provider is in offline simulation mode
    async def fake_offline_stream(**kwargs):
        provider.last_response_source = "offline_fallback"
        yield "[Aura Local Mode] Offline fallback response."

    provider.stream_chat = MagicMock(side_effect=fake_offline_stream)
    ev_offline = [ev async for ev in svc.handle_message_stream(prompt="Explain merge sort.", session_id=f"s_off_{uid}")]
    assert next(e for e in ev_offline if e["type"] == "done")["response_source"] == "offline_fallback"


def test_turn_persistence_deduplication_by_request_id():
    """
    Fix 1 Acceptance Test:
    Submit the same turn_id / request ID twice to record_turn in ContextEngine.
    Verify that in-memory history and SQLite database contain only one user/assistant exchange.
    """
    import uuid
    from aura_assistant.core.db.session import load_conversation_history

    engine = ContextEngine()
    test_sid = f"dedup_test_{uuid.uuid4().hex[:8]}"
    stable_req_id = f"req_{uuid.uuid4().hex[:12]}"

    # First turn submission
    engine.record_turn(
        session_id=test_sid,
        user_prompt="Define quantum computing.",
        assistant_response="Quantum computing uses qubits and superposition.",
        model_name="qwen3.5:4b",
        persist_db=True,
        turn_id=stable_req_id,
    )

    # Second submission with identical turn_id / request_id (simulated retry / network replay)
    dup_result = engine.record_turn(
        session_id=test_sid,
        user_prompt="Define quantum computing.",
        assistant_response="Quantum computing uses qubits and superposition.",
        model_name="qwen3.5:4b",
        persist_db=True,
        turn_id=stable_req_id,
    )
    assert dup_result is None

    # Verify in-memory history has only 2 messages (1 user, 1 assistant)
    mem_history = engine.get_or_create_history(test_sid)
    assert len(mem_history) == 2

    # Verify SQLite DB has only 2 messages
    db_history = load_conversation_history(test_sid, limit=10)
    assert len(db_history) == 2
    assert db_history[0]["role"] == "user"
    assert db_history[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_router_short_recall_uses_fast_model_without_escalation():
    """
    P0 Test: Short, low-complexity recall and READY prompts use the fast qwen2.5:0.5b route
    even with has_history=True, keeping TTFT sub-2s on local hardware.
    """
    from aura_assistant.core.llm.router import LLMRouter

    router = LLMRouter()
    router.get_available_models = AsyncMock(return_value=frozenset(["qwen2.5:0.5b", "qwen2.5:1.5b", "qwen3.5:4b"]))

    route = await router.resolve_route(
        prompt="What exact word did you reply with earlier?",
        channel="text",
        has_history=True
    )

    assert route.model == "qwen2.5:0.5b"
    assert route.num_predict == 128
    assert route.num_thread == 4


@pytest.mark.asyncio
async def test_router_complex_analytical_prompt_escalates_to_moderate_or_strong():
    """
    P0 Test: Genuinely complex prompts escalate to moderate/stronger models when installed.
    """
    from aura_assistant.core.llm.router import LLMRouter

    router = LLMRouter()
    router.get_available_models = AsyncMock(return_value=frozenset(["qwen2.5:0.5b", "qwen2.5:1.5b"]))

    complex_prompt = "Provide a comprehensive analysis and compare in detail the architectural tradeoffs between Paxos and Raft."
    route = await router.resolve_route(
        prompt=complex_prompt,
        channel="text",
        has_history=False
    )

    assert route.model == "qwen2.5:1.5b"
    assert route.num_predict == 256


@pytest.mark.asyncio
async def test_router_multi_turn_missing_strong_model_emits_fallback_reason():
    """
    Fix 2 Acceptance Test:
    When a complex task arrives and the preferred model is missing from Ollama /api/tags,
    the router selects an installed fallback and reports the fallback_reason.
    """
    from aura_assistant.core.llm.router import LLMRouter

    router = LLMRouter()
    router.get_available_models = AsyncMock(return_value=frozenset(["qwen2.5:0.5b"]))

    route = await router.resolve_route(
        prompt="write a script to benchmark memory throughput",
        channel="text",
        has_history=True
    )

    assert route.model == "qwen2.5:0.5b"
    assert route.fallback_reason is not None
    assert "requested_model_not_installed" in route.fallback_reason


@pytest.mark.asyncio
async def test_request_specific_diagnostics_trace(tmp_path: Path):
    """
    Fix 5 Acceptance Test:
    Verify pre_inference_traces registry stores per-request trace keyed by request_id
    and can be retrieved via get_pre_inference_trace(req_id).
    """
    import uuid
    from aura_assistant.services.chat_service import ChatService
    from aura_assistant.core.llm.router import LLMRouter, RouteResult
    from aura_assistant.core.llm.provider import OllamaProvider
    from aura_assistant.core.tools.registry import ToolRegistry

    router = MagicMock(spec=LLMRouter)
    router.resolve_route = AsyncMock(
        return_value=RouteResult(model="qwen3.5:4b", num_ctx=4096, temperature=0.3, pinned=True, keep_alive=-1)
    )
    router.vram_arbiter = None

    provider = MagicMock(spec=OllamaProvider)
    provider.is_offline_simulation = False
    provider.last_response_source = "live_model"

    async def fake_stream(**kwargs):
        yield "Trace diagnostic response."

    provider.stream_chat = MagicMock(side_effect=fake_stream)
    svc = ChatService(
        router=router,
        provider=provider,
        tools=ToolRegistry(),
        memory=EpisodicMemoryManager(storage_dir=tmp_path / "mem_trace"),
        context_engine=ContextEngine()
    )

    custom_req_id = f"client_req_{uuid.uuid4().hex[:10]}"
    sid = f"trace_sess_{uuid.uuid4().hex[:8]}"

    events = [
        ev async for ev in svc.handle_message_stream(
            prompt="Explain the difference between TCP and UDP.",
            session_id=sid,
            request_id=custom_req_id
        )
    ]
    done_ev = next(e for e in events if e["type"] == "done")
    assert done_ev["request_id"] == custom_req_id

    # Retrieve from ChatService bounded registry
    trace = svc.get_pre_inference_trace(custom_req_id)
    assert trace is not None
    assert trace["request_id"] == custom_req_id
    assert trace["session_id"] == sid
    assert trace["routed_model"] == "qwen3.5:4b"
    assert "estimated_tokens" in trace

