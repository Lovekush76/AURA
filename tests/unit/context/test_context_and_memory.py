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
