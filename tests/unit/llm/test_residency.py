import pytest
from unittest.mock import AsyncMock, patch
from aura_assistant.core.llm.router import LLMRouter

@pytest.mark.asyncio
async def test_warm_pinned_models_locks_voice_model():
    router = LLMRouter()
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        await router.warm_pinned_models()
        mock_post.assert_called_once()
        sent_json = mock_post.call_args[1]["json"]
        assert sent_json["model"] == "qwen3.5:4b"
        assert sent_json["keep_alive"] == -1

@pytest.mark.asyncio
async def test_voice_channel_preserves_pinned_model():
    router = LLMRouter()
    route = await router.resolve_route("write a python script to test", channel="voice")
    # Even if coding markers exist, voice channel stays pinned to voice slot
    assert route.model == "qwen3.5:4b"
    assert route.pinned is True

@pytest.mark.asyncio
async def test_heavy_model_swapping_serialized():
    router = LLMRouter()
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        # Switch to code heavy model
        await router.resolve_route("def execute_order_66(): pass", channel="text")
        assert router.current_heavy_model == "qwen3-coder:30b"

        # Switch to reasoning heavy model: should unload coder first
        await router.resolve_route("deep analysis and prove this theorem", channel="text")
        assert router.current_heavy_model == "deepseek-r1:14b"
        
        # Verify unload call was made for qwen3-coder:30b
        unload_calls = [c for c in mock_post.call_args_list if c[1]["json"].get("keep_alive") == 0]
        assert len(unload_calls) >= 1
        assert unload_calls[0][1]["json"]["model"] == "qwen3-coder:30b"
