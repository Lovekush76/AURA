import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aura_assistant.core.llm.router import LLMRouter
from aura_assistant.core.llm.residency import VRAMArbiter
from aura_assistant.core.llm.provider import OllamaProvider


@pytest.mark.asyncio
async def test_warm_pinned_models_locks_voice_model():
    router = LLMRouter()
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        ok = await router.warm_pinned_models()
        assert ok is True
        mock_post.assert_called_once()
        sent_json = mock_post.call_args[1]["json"]
        assert sent_json["model"] == "qwen3.5:4b"
        assert sent_json["keep_alive"] == -1
    await router.aclose()


@pytest.mark.asyncio
async def test_voice_channel_preserves_pinned_model_and_keep_alive():
    router = LLMRouter()
    router._cached_available_models = frozenset({"qwen3.5:4b", "qwen2.5:0.5b", "qwen3-coder:30b"})
    router._tags_valid_until = 9999999999.0

    route = await router.resolve_route("write a python script to test", channel="voice")
    assert route.model == "qwen3.5:4b"
    assert route.pinned is True
    assert route.keep_alive == -1
    assert route.num_ctx == 1536
    await router.aclose()


@pytest.mark.asyncio
async def test_heavy_model_swapping_serialized_and_uses_finite_keep_alive():
    arbiter = VRAMArbiter(vram_ceiling_mb=24576, safety_headroom_mb=1024)
    router = LLMRouter(vram_arbiter=arbiter)
    router._cached_available_models = frozenset({
        "qwen3.5:4b", "qwen2.5:0.5b", "qwen3-coder:30b", "deepseek-r1:14b"
    })
    router._tags_valid_until = 9999999999.0

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": []}
        mock_post.return_value = mock_resp
        mock_get.return_value = mock_resp

        # 1. Switch to code heavy model (30B) - must pass VRAMArbiter admission
        r_code = await router.resolve_route("def execute_order_66(): pass", channel="text")
        assert r_code.model == "qwen3-coder:30b"
        assert r_code.pinned is False
        assert r_code.keep_alive == "10m"
        assert router.current_heavy_model == "qwen3-coder:30b"

        # 2. Switch to reasoning heavy model: should unload coder first
        r_reason = await router.resolve_route("deep analysis and prove this theorem", channel="text")
        assert r_reason.model == "deepseek-r1:14b"
        assert r_reason.pinned is False
        assert r_reason.keep_alive == "10m"
        assert router.current_heavy_model == "deepseek-r1:14b"

        unload_calls = [c for c in mock_post.call_args_list if c[1]["json"].get("keep_alive") == 0]
        assert len(unload_calls) >= 1
        assert unload_calls[0][1]["json"]["model"] == "qwen3-coder:30b"
    await router.aclose()


@pytest.mark.asyncio
async def test_override_model_goes_through_residency_and_falls_back_on_insufficient_vram():
    # Constrained 8GB VRAM ceiling: 30B and 14B must be rejected and safely fall back to pinned model
    arbiter = VRAMArbiter(vram_ceiling_mb=8192, safety_headroom_mb=1024)
    router = LLMRouter(vram_arbiter=arbiter)
    router._cached_available_models = frozenset({
        "qwen3.5:4b", "qwen2.5:0.5b", "qwen3-coder:30b", "deepseek-r1:14b"
    })
    router._tags_valid_until = 9999999999.0

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": []}
        mock_get.return_value = mock_resp

        # Requesting deepseek-r1:14b via override_model on 8GB GPU must NOT return deepseek-r1:14b
        route = await router.resolve_route("hello", channel="text", override_model="deepseek-r1:14b")
        assert route.model == "qwen3.5:4b"
        assert route.pinned is True
        assert route.keep_alive == -1
        assert route.fallback_reason == "residency_admission_rejected:deepseek-r1:14b"

        # Small model override (qwen2.5:0.5b) must get its authoritative 2048 context, not 32768
        small_route = await router.resolve_route("hello", channel="text", override_model="qwen2.5:0.5b")
        assert small_route.model == "qwen2.5:0.5b"
        assert small_route.num_ctx == 2048
        assert small_route.keep_alive == -1
    await router.aclose()


@pytest.mark.asyncio
async def test_concurrent_heavy_swaps_serialized_and_failed_load_falls_back():
    arbiter = VRAMArbiter(vram_ceiling_mb=24576, safety_headroom_mb=1024)
    router = LLMRouter(vram_arbiter=arbiter)
    router._cached_available_models = frozenset({
        "qwen3.5:4b", "qwen2.5:0.5b", "qwen3-coder:30b", "deepseek-r1:14b"
    })
    router._tags_valid_until = 9999999999.0

    # Simulate failed Ollama preload (HTTP 500) -> must fall back to pinned model
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        fail_resp = MagicMock()
        fail_resp.status_code = 500
        mock_post.return_value = fail_resp

        ok_get = MagicMock()
        ok_get.status_code = 200
        ok_get.json.return_value = {"models": []}
        mock_get.return_value = ok_get

        r1, r2 = await asyncio.gather(
            router.resolve_route("def foo(): pass", channel="text"),
            router.resolve_route("prove this theorem", channel="text")
        )
        assert r1.model == "qwen3.5:4b"
        assert r1.fallback_reason == "residency_admission_rejected:qwen3-coder:30b"
        assert r2.model == "qwen3.5:4b"
        assert r2.fallback_reason == "residency_admission_rejected:deepseek-r1:14b"
    await router.aclose()


@pytest.mark.asyncio
async def test_shared_client_and_cache_ttl_invalidation_and_offline_backoff():
    router = LLMRouter(cache_ttl_seconds=30.0, offline_backoff_seconds=5.0)
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "models": [
                {"name": "qwen3.5:4b:latest"},
                {"name": "my:latest:custom:latest"}
            ]
        }
        mock_get.return_value = resp

        models1 = await router.get_available_models()
        models2 = await router.get_available_models()
        assert mock_get.call_count == 1  # Cached within 30s TTL
        assert isinstance(models1, frozenset)
        assert "qwen3.5:4b" in models1
        # Trailing :latest stripped, internal :latest preserved
        assert "my:latest:custom" in models1

        # Invalidate cache for missing model
        router.invalidate_model_cache("qwen3.5:4b")
        assert "qwen3.5:4b" not in router._cached_available_models

        # Simulate offline error -> 5s backoff prevents repeated HTTP calls
        mock_get.side_effect = RuntimeError("Connection refused")
        await router.get_available_models(force_refresh=True)
        calls_after_fail = mock_get.call_count
        await router.get_available_models()
        assert mock_get.call_count == calls_after_fail  # Backoff prevented duplicate call
    await router.aclose()
