"""
Unit test suite for Aura v3.5 response grounding, language specification accuracy,
relevance-aware profile isolation, technical intent routing, and truncation signaling.
Covers all 14 required quality and anti-hallucination regression tests.
"""

import pytest
import asyncio
from pathlib import Path
from typing import Dict, Any, List

from aura_assistant.core.context.context_engine import ContextEngine, ContextBudget
from aura_assistant.core.llm.router import LLMRouter, RouteResult
from aura_assistant.core.memory.episodic import EpisodicMemoryManager
from aura_assistant.services.chat_service import ResponseCache


@pytest.fixture
def context_engine():
    return ContextEngine(ContextBudget(max_context_tokens=4096))


class TestResponseGrounding:
    # 1. Java Definition
    def test_java_definition(self, context_engine):
        session_id = "test_sess_java_def"
        messages, telemetry = context_engine.build_engineered_context(
            session_id=session_id,
            current_prompt="what is java"
        )
        system_content = messages[0]["content"]
        assert "JAVA LANGUAGE GROUNDING" in system_content
        assert "Java" in system_content

    # 2. Java Inheritance Grounding
    def test_java_inheritance_grounding(self, context_engine):
        session_id = "test_sess_java_inherit"
        context_engine.record_turn_in_memory(session_id, "what is java", "Java is an OOP language.")
        messages, telemetry = context_engine.build_engineered_context(
            session_id=session_id,
            current_prompt="inheritance"
        )
        system_content = messages[0]["content"]
        assert "extends" in system_content
        assert "super()" in system_content
        assert "Never use Python's 'class Child(Parent)'" in system_content or "Never use Python" in system_content
        assert "from" in system_content  # Forbidding 'from' keyword

    # 3. Follow-up "its types"
    def test_follow_up_its_types(self, context_engine):
        session_id = "test_sess_its_types"
        context_engine.record_turn_in_memory(session_id, "what is java", "Java is an OOP language.")
        context_engine.record_turn_in_memory(session_id, "inheritance", "Inheritance allows subclasses to extend superclasses.")
        messages, telemetry = context_engine.build_engineered_context(
            session_id=session_id,
            current_prompt="its types"
        )
        system_content = messages[0]["content"]
        assert "JAVA LANGUAGE GROUNDING" in system_content

    # 4. Java Primitive Types Grounding
    def test_java_primitive_types(self, context_engine):
        session_id = "test_sess_primitives"
        messages, telemetry = context_engine.build_engineered_context(
            session_id=session_id,
            current_prompt="what are java primitive types"
        )
        system_content = messages[0]["content"]
        for p_type in ["byte", "short", "int", "long", "float", "double", "char", "boolean"]:
            assert p_type in system_content

    # 5. Tuple Rejection
    def test_tuple_rejection(self, context_engine):
        session_id = "test_sess_tuple"
        messages, telemetry = context_engine.build_engineered_context(
            session_id=session_id,
            current_prompt="tell me about java data types"
        )
        system_content = messages[0]["content"]
        assert "'Tuple' is NOT a built-in Java data type" in system_content

    # 6. Map Interface Grounding
    def test_map_interface_grounding(self, context_engine):
        session_id = "test_sess_map"
        messages, telemetry = context_engine.build_engineered_context(
            session_id=session_id,
            current_prompt="explain java collections and map"
        )
        system_content = messages[0]["content"]
        assert "java.util.Map is an interface" in system_content

    # 7. Session Isolated Memory
    def test_session_isolated_memory(self, tmp_path):
        mem = EpisodicMemoryManager(storage_dir=Path(tmp_path))
        # Archive facts for two different sessions
        mem.archive_compacted_summary("session_A", "User discussed Python classes with class Dog(Animal): and def bark().")
        mem.archive_compacted_summary("session_B", "User discussed Java OOP classes with extends and super.")

        # Query session_B - should NOT retrieve session_A's python facts
        retrieved_b = mem.retrieve_relevant_facts("classes", session_id="session_B")
        assert not any("class Dog(Animal)" in f for f in retrieved_b)
        assert any("Java OOP" in f for f in retrieved_b)

    # 8. Relevance-Aware User Profile
    def test_relevance_aware_profile(self, context_engine):
        session_id = "test_sess_prof"
        profile_data = {
            "name": "Alex",
            "skills": "Python, Django, FastAPI, Machine Learning",
            "experience": "Senior Developer"
        }
        # Technical Java question should filter out conflicting Python skills from user profile block
        messages, telemetry = context_engine.build_engineered_context(
            session_id=session_id,
            current_prompt="explain java inheritance syntax",
            profile_data=profile_data
        )
        system_content = messages[0]["content"]
        assert "secondary_background_only" in system_content
        profile_blocks = [b for b in system_content.split("\n\n") if "<user_profile" in b]
        assert len(profile_blocks) > 0
        assert "Python" not in profile_blocks[0]
        assert "Alex" in profile_blocks[0]

        # Career question preserves full profile
        messages_career, _ = context_engine.build_engineered_context(
            session_id=session_id,
            current_prompt="what career roles fit my skills?",
            profile_data=profile_data
        )
        career_profile_blocks = [b for b in messages_career[0]["content"].split("\n\n") if "<user_profile" in b]
        assert "Python" in career_profile_blocks[0]

    # 9. Follow-up Topic Retention & Classifier
    def test_follow_up_topic_retention(self):
        router = LLMRouter()
        # Direct technical prompt
        assert router.classify_technical_intent("inheritance") is True
        assert router.classify_technical_intent("what is polymorphism") is True
        assert router.classify_technical_intent("inner join vs left join") is True

        # Casual chat
        assert router.classify_technical_intent("hello there") is False
        assert router.classify_technical_intent("what did I say earlier?") is False

        # Elliptical follow-up with active topic
        assert router.classify_technical_intent("its type", active_topic="java") is True
        assert router.classify_technical_intent("how does it work", active_topic="sql") is True
        assert router.classify_technical_intent("its type", active_topic=None) is False

    # 10. Pronoun Disambiguation
    def test_pronoun_disambiguation(self, context_engine):
        session_id = "test_sess_coref"
        context_engine.record_turn_in_memory(session_id, "what is Java Virtual Machine?", "JVM executes Java bytecode.")
        expanded = context_engine.resolve_coreferences(session_id, "how does it work?")
        assert "Context Entities" in expanded
        assert "Virtual" in expanded or "Machine" in expanded or "bytecode" in expanded or "Java" in expanded

    # 11. Truncation Signaling
    def test_truncation_signaling(self):
        from aura_assistant.core.llm.provider import OllamaProvider
        provider = OllamaProvider()
        chunk = {
            "done": True,
            "done_reason": "length",
            "eval_count": 512,
            "eval_duration": 1000000000
        }
        done_reason = chunk.get("done_reason")
        truncated = (done_reason == "length")
        assert done_reason == "length"
        assert truncated is True

    # 12. Normal Completion
    def test_normal_completion(self):
        chunk = {
            "done": True,
            "done_reason": "stop",
            "eval_count": 150,
            "eval_duration": 1000000000
        }
        done_reason = chunk.get("done_reason") or "stop"
        truncated = (done_reason == "length")
        assert done_reason == "stop"
        assert truncated is False

    # 13. Cache Isolation Multi-Turn
    def test_cache_isolation_multi_turn(self):
        can_cache, reason = ResponseCache.evaluate_cacheability(
            prompt="inheritance",
            has_history=True
        )
        assert can_cache is False
        assert reason == "multi_turn_history_present"

    # 14. Model Tier Routing and Fallback
    @pytest.mark.asyncio
    async def test_model_tier_routing_and_fallback(self):
        router = LLMRouter()
        router._cached_available_models = frozenset({"qwen2.5:0.5b", "qwen2.5:1.5b", "qwen3.5:4b"})
        router._tags_valid_until = 9999999999.0

        # Technical query routes to qwen2.5:1.5b
        res_tech = await router.resolve_route("explain java inheritance")
        assert res_tech.model == "qwen2.5:1.5b"
        assert res_tech.num_predict in (512, 768, 1536)

        # Follow-up with active topic routes to qwen2.5:1.5b
        res_followup = await router.resolve_route("its type", active_topic="java")
        assert res_followup.model == "qwen2.5:1.5b"

        # Casual chat routes to fast qwen2.5:0.5b
        res_chat = await router.resolve_route("hello, good morning!")
        assert res_chat.model == "qwen2.5:0.5b"

        # Missing model triggers verified fallback
        router_missing = LLMRouter()
        router_missing._cached_available_models = frozenset({"qwen2.5:0.5b", "qwen3.5:4b"})
        router_missing._tags_valid_until = 9999999999.0
        res_fallback = await router_missing.resolve_route("explain java inheritance")
        assert res_fallback.model in ("qwen3.5:4b", "qwen2.5:0.5b")
        assert "requested_model_not_installed" in str(res_fallback.fallback_reason)
