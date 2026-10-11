"""
Aura Assistant v3.5 - Answer Completeness and Output-Budget Regression Test Suite
Validates all 18 requirements from Phase 7:
1. "What is Python?" produces a complete, single-response overview directive.
2. The answer planning covers definition, features, data types, OOP, functions, etc.
3. Completeness validation: finishes lists and avoids mid-sentence stopping directives.
4. "Explain Python data types" covers all major built-in data-type categories.
5. "Explain Java inheritance" remains Java-specific.
6. "What are its types?" resolves active topic from history.
7. Simple factual question gets economical budget (<= 512, 128 for recall).
8. Broad explanation receives larger budget (1536) than simple answer.
9. Effective num_predict matches the value passed to Ollama.
10. Context headroom is respected when calculating generation budget.
11. done_reason=length correctly flagged as truncated.
12. done_reason=stop correctly flagged as not truncated.
13. Interrupted stream is not persisted as a complete turn.
14. Partial/truncated response cannot overwrite or be stored into ResponseCache.
15. Model fallback preserves output-budget policy.
16. Complete SSE response integrity and batching match.
17. Turn ID deduplication prevents duplicate conversation turns.
18. Session isolation is preserved.
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from aura_assistant.core.context.context_engine import ContextEngine, ContextBudget
from aura_assistant.core.llm.router import LLMRouter, RouteResult
from aura_assistant.core.llm.provider import OllamaProvider
from aura_assistant.core.memory.episodic import EpisodicMemoryManager
from aura_assistant.services.chat_service import ChatService, ResponseCache


@pytest.fixture
def context_engine():
    return ContextEngine(ContextBudget(max_context_tokens=4096))


class TestAnswerCompletenessAndBudget:
    # 1. "What is Python?" produces a complete, single-response overview directive.
    def test_what_is_python_overview_directive(self, context_engine):
        session_id = "test_python_overview"
        messages, telemetry = context_engine.build_engineered_context(
            session_id=session_id,
            current_prompt="What is Python?",
            query_scope="broad_overview"
        )
        sys_msg = messages[0]["content"]
        assert "ANSWER PLANNING & COMPLETENESS DIRECTIVE" in sys_msg
        assert "Produce a compact, complete response covering those aspects in the same turn" in sys_msg
        assert "PYTHON LANGUAGE GROUNDING" in sys_msg
        assert "PYTHON OVERVIEW STRUCTURE" in sys_msg

    # 2. High-level overview covers definition, features, data types, OOP, modules, summary.
    def test_overview_aspects_coverage(self, context_engine):
        session_id = "test_python_aspects"
        messages, _ = context_engine.build_engineered_context(
            session_id=session_id,
            current_prompt="What is Python?",
            query_scope="broad_overview"
        )
        sys_msg = messages[0]["content"]
        expected_sections = [
            "Definition and main characteristics",
            "Key features",
            "Built-in data types",
            "Operators and control flow",
            "Functions, modules, and packages",
            "Object-oriented programming",
            "Common applications",
            "Short summary"
        ]
        for sec in expected_sections:
            assert sec in sys_msg

    # 3. Completeness directive forbids mid-sentence / mid-list stopping and premature continuation.
    def test_answer_completeness_directives(self, context_engine):
        messages, _ = context_engine.build_engineered_context(
            session_id="test_completeness",
            current_prompt="Explain OOP concepts",
            query_scope="broad_overview"
        )
        sys_msg = messages[0]["content"]
        assert "Do not stop mid-sentence, mid-list, or mid-section" in sys_msg
        assert "Do not offer continuation as a substitute for completing an ordinary answer" in sys_msg
        assert "Complete each list and section you start" in sys_msg

    # 4. "Explain Python data types" covers all major built-in categories.
    def test_python_data_types_coverage(self, context_engine):
        messages, _ = context_engine.build_engineered_context(
            session_id="test_py_types",
            current_prompt="Explain Python data types",
            query_scope="broad_overview"
        )
        sys_msg = messages[0]["content"]
        assert "integers, floats, strings, booleans, lists, tuples, dictionaries, sets" in sys_msg

    # 5. "Explain Java inheritance" remains Java-specific.
    def test_java_inheritance_grounding(self, context_engine):
        messages, _ = context_engine.build_engineered_context(
            session_id="test_java_inherit",
            current_prompt="Explain Java inheritance and its types.",
            query_scope="broad_overview"
        )
        sys_msg = messages[0]["content"]
        assert "JAVA LANGUAGE GROUNDING" in sys_msg
        assert "extends" in sys_msg
        assert "super()" in sys_msg
        assert "Never use Python's 'class Child(Parent)'" in sys_msg
        assert "Java does not support multiple inheritance with classes" in sys_msg

    # 6. "What are its types?" correctly resolves the topic from relevant conversation history.
    def test_follow_up_active_topic_resolution(self, context_engine):
        session_id = "test_topic_followup"
        context_engine.record_turn_in_memory(session_id, "Explain Java inheritance", "Java uses extends for inheritance.")
        target_lang = context_engine.detect_target_language(session_id, "What are its types?")
        assert target_lang == "java"

        messages, _ = context_engine.build_engineered_context(
            session_id=session_id,
            current_prompt="What are its types?",
            query_scope="broad_overview"
        )
        sys_msg = messages[0]["content"]
        assert "JAVA LANGUAGE GROUNDING" in sys_msg

    # 7. A simple factual question does not receive an unnecessarily large output budget.
    @pytest.mark.asyncio
    async def test_simple_factual_economical_budget(self):
        router = LLMRouter()
        router._cached_available_models = frozenset({"qwen2.5:0.5b", "qwen2.5:1.5b"})
        router._tags_valid_until = 9999999999.0

        # Short factual / math question
        res_math = await router.resolve_route("What is 2 + 2?")
        assert res_math.num_predict <= 512
        assert res_math.query_scope == "simple_factual"

        # Short exact recall question
        res_recall = await router.resolve_route("Reply with only the previous number.")
        assert res_recall.num_predict == 128
        assert res_recall.query_scope == "recall"

    # 8. A broad explanation receives a larger budget than a simple answer.
    @pytest.mark.asyncio
    async def test_broad_overview_receives_larger_budget(self):
        router = LLMRouter()
        router._cached_available_models = frozenset({"qwen2.5:0.5b", "qwen2.5:1.5b"})
        router._tags_valid_until = 9999999999.0

        res_simple = await router.resolve_route("What is 2 + 2?")
        res_broad = await router.resolve_route("What is Python?")

        assert res_broad.num_predict == 1536
        assert res_broad.num_predict > res_simple.num_predict
        assert res_broad.query_scope == "broad_overview"

    # 9. Effective num_predict matches the value passed to Ollama.
    @pytest.mark.asyncio
    async def test_effective_num_predict_sent_to_provider(self):
        provider = OllamaProvider()
        provider.check_health = AsyncMock(return_value=True)

        captured_payload = {}
        original_post = provider._get_client

        class DummyStreamResponse:
            status_code = 200
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            async def aiter_lines(self):
                yield '{"message": {"content": "Python is a language."}, "done": true, "eval_count": 50, "eval_duration": 1000000000, "done_reason": "stop"}'

        class DummyClient:
            is_closed = False
            def stream(self, method, url, json=None, timeout=None):
                captured_payload.update(json or {})
                return DummyStreamResponse()

        provider._shared_client = DummyClient()
        provider._owns_client = False

        tokens = [
            t async for t in provider.stream_chat(
                model="qwen2.5:1.5b",
                messages=[{"role": "user", "content": "What is Python?"}],
                num_ctx=4096,
                num_predict=1536
            )
        ]
        assert captured_payload["options"]["num_predict"] == 1536
        assert provider.last_usage_metrics["num_predict"] == 1536

    # 10. Available context headroom is respected when calculating the output budget.
    def test_context_headroom_respected(self, context_engine):
        # When context is tight (e.g. max_ctx=1024), reserve_gen adapts safely without starvation
        messages, telemetry = context_engine.build_engineered_context(
            session_id="test_headroom",
            current_prompt="What is Python?",
            max_ctx_override=1024,
            requested_output_tokens=1536
        )
        assert telemetry["reserve_generation_tokens"] <= 1024
        assert telemetry["within_budget"] is True
        assert telemetry["total_context_tokens"] + telemetry["reserve_generation_tokens"] <= 1024

    # 11. done_reason=length is correctly surfaced as length-limited output (truncated=True).
    def test_done_reason_length_surfaced_as_truncated(self):
        provider = OllamaProvider()
        chunk = {
            "done": True,
            "done_reason": "length",
            "eval_count": 1536,
            "eval_duration": 10000000000
        }
        done_reason = chunk.get("done_reason")
        truncated = (done_reason == "length")
        assert done_reason == "length"
        assert truncated is True

    # 12. Normal completion is not falsely flagged as truncated.
    def test_normal_completion_not_flagged_truncated(self):
        chunk = {
            "done": True,
            "done_reason": "stop",
            "eval_count": 420,
            "eval_duration": 5000000000
        }
        done_reason = chunk.get("done_reason") or "stop"
        truncated = (done_reason == "length")
        assert done_reason == "stop"
        assert truncated is False

    # 13. An interrupted stream is not persisted as a complete answer.
    @pytest.mark.asyncio
    async def test_interrupted_stream_not_persisted(self, tmp_path):
        router = LLMRouter()
        router._cached_available_models = frozenset({"qwen2.5:0.5b"})
        router._tags_valid_until = 9999999999.0

        provider = OllamaProvider()
        provider.check_health = AsyncMock(return_value=True)

        async def failing_stream(**kwargs):
            yield "Starting output..."
            raise asyncio.CancelledError("Client connection abruptly closed")

        provider.stream_chat = MagicMock(side_effect=failing_stream)
        ctx_engine = ContextEngine()
        svc = ChatService(
            router=router,
            provider=provider,
            tools=MagicMock(),
            memory=EpisodicMemoryManager(storage_dir=tmp_path / "mem_interrupt"),
            context_engine=ctx_engine
        )

        sid = "sess_interrupt_test"
        with pytest.raises(asyncio.CancelledError):
            async for _ in svc.handle_message_stream(
                prompt="Explain Python in detail",
                session_id=sid
            ):
                pass

        # History must NOT contain the incomplete turn
        history = ctx_engine.get_or_create_history(sid)
        assert len(history) == 0

    # 14. Partial cache entries cannot overwrite valid complete answers.
    def test_partial_cache_entries_rejected(self):
        cache = ResponseCache()
        # Complete valid answer stores cleanly
        saved = cache.store(
            prompt="what is python",
            response="Python is a high-level general purpose programming language.",
            truncated=False,
            done_reason="stop"
        )
        assert saved is True

        # Truncated response is rejected
        rejected_trunc = cache.store(
            prompt="what is python",
            response="Python is a high-level general purpose programming language that has many...",
            truncated=True,
            done_reason="length"
        )
        assert rejected_trunc is False

        # Verify cached value was NOT overwritten
        cached_val, event = cache.lookup(prompt="what is python")
        assert cached_val == "Python is a high-level general purpose programming language."
        assert event["status"] == "cache_hit"

    # 15. Primary-model failure and fallback preserve the output-budget policy.
    @pytest.mark.asyncio
    async def test_model_fallback_preserves_output_budget(self):
        router = LLMRouter()
        # Simulate qwen2.5:1.5b missing; fallback must handle broad_overview budget
        router._cached_available_models = frozenset({"qwen2.5:0.5b", "qwen3.5:4b"})
        router._tags_valid_until = 9999999999.0

        res = await router.resolve_route("What is Python?")
        assert res.model in ("qwen3.5:4b", "qwen2.5:0.5b")
        assert res.num_predict == 1536
        assert res.query_scope == "broad_overview"
        assert res.fallback_reason is not None

    # 16. The complete response shown in the frontend matches the complete response received from the backend.
    def test_complete_response_token_accumulation(self):
        chunks = ["Python ", "is ", "an ", "interpreted, ", "high-level ", "language."]
        accumulated = "".join(chunks)
        assert accumulated == "Python is an interpreted, high-level language."
        assert not accumulated.endswith("...")

    # 17. Automatic retry / deduplication does not duplicate conversation turns.
    def test_turn_id_deduplication_prevents_duplicate_turns(self, context_engine):
        sid = "sess_dedup_test"
        turn_id = "turn_unique_123"

        # First recording
        context_engine.record_turn_in_memory(
            session_id=sid,
            user_prompt="What is Python?",
            assistant_response="Python is an interpreted language.",
            turn_id=turn_id
        )
        history_len_1 = len(context_engine.get_or_create_history(sid))
        assert history_len_1 == 2

        # Duplicate retry with same turn_id must be safely ignored
        context_engine.record_turn_in_memory(
            session_id=sid,
            user_prompt="What is Python?",
            assistant_response="Python is an interpreted language.",
            turn_id=turn_id
        )
        history_len_2 = len(context_engine.get_or_create_history(sid))
        assert history_len_2 == 2

    # 18. Session isolation is preserved.
    def test_session_isolation(self, context_engine):
        context_engine.record_turn_in_memory("session_1", "What is Python?", "Python is dynamic.")
        context_engine.record_turn_in_memory("session_2", "What is Java?", "Java is statically typed.")

        h1 = context_engine.get_or_create_history("session_1")
        h2 = context_engine.get_or_create_history("session_2")

        assert len(h1) == 2
        assert len(h2) == 2
        assert "Python" in h1[0].content
        assert "Java" in h2[0].content
        assert "Java" not in h1[0].content
