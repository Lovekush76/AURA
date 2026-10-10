import asyncio
import threading
import numpy as np
import pytest
from aura_assistant.core.voice.gating import BiometricGating
from aura_assistant.core.voice.formatter import VoiceFormatter
from daemons.voice.daemon import VoiceDaemon


def test_biometric_gating_strips_sensitive_tools_under_threshold():
    tools_cfg = {
        "tools": {
            "run_code": {"sensitivity": "personal", "requires_voice_match": True},
            "patch_filesystem": {"sensitivity": "critical", "requires_voice_match": True},
            "web_search": {"sensitivity": "public", "requires_voice_match": False}
        }
    }
    gating = BiometricGating(tools_cfg)

    # 1. Voice channel with low score (< 0.85): personal & critical tools must be stripped
    allowed = gating.filter_allowed_tools(
        available_tool_names=["run_code", "patch_filesystem", "web_search"],
        speaker_verified=False,
        biometric_score=0.72,
        channel="voice"
    )
    assert allowed == ["web_search"]

    # 2. Voice channel with high score (>= 0.85): all tools allowed
    authorized = gating.filter_allowed_tools(
        available_tool_names=["run_code", "patch_filesystem", "web_search"],
        speaker_verified=True,
        biometric_score=0.91,
        channel="voice"
    )
    assert len(authorized) == 3

    # 3. Text channel: all tools allowed
    text_allowed = gating.filter_allowed_tools(
        available_tool_names=["run_code", "patch_filesystem", "web_search"],
        speaker_verified=False,
        biometric_score=0.0,
        channel="text"
    )
    assert len(text_allowed) == 3


def test_voice_formatter_sanitization():
    raw_markdown = """
# System Diagnostics
Here is the code:
```python
def secret(): pass
```
Check this [documentation](https://aura.local) for details.
Equation: $E = mc^2$
- Item 1
- Item 2
"""
    spoken = VoiceFormatter.format_for_speech(raw_markdown)
    assert "```" not in spoken
    assert "https://" not in spoken
    assert "#" not in spoken
    assert "System Diagnostics" in spoken
    assert "equation" in spoken or "E = mc^2" in spoken

    sentences = VoiceFormatter.split_into_sentences("Hello there. How are you today? I am ready!")
    assert len(sentences) == 3


@pytest.mark.asyncio
async def test_voice_daemon_honest_biometrics_and_threadsafe_bounded_queue():
    daemon = VoiceDaemon(max_queue_frames=4)
    daemon._loop = asyncio.get_running_loop()

    try:
        # 1. Honest unverified state when no biometric model / voiceprint is enrolled
        dummy_audio = np.zeros(1280, dtype=np.float32)
        verified, score, status = daemon.verify_speaker_biometrics(dummy_audio)
        assert verified is False
        assert score == 0.0
        assert status == "unverified_no_biometric_model"

        # 2. Simulate PortAudio C thread pushing 10 frames into a maxsize=4 queue
        indata = np.ones((1280, 1), dtype=np.float32) * 0.1

        def _portaudio_thread_worker():
            for _ in range(10):
                daemon.audio_callback(indata, 1280, None, None)

        t = threading.Thread(target=_portaudio_thread_worker)
        t.start()
        t.join(timeout=2.0)

        # Allow loop.call_soon_threadsafe callbacks to drain
        await asyncio.sleep(0.05)

        assert daemon.audio_queue.qsize() == 4
        assert daemon.dropped_frames_count == 6
        diag = daemon.get_diagnostics()
        assert diag["dropped_frames_count"] == 6
        assert diag["queue_maxsize"] == 4
    finally:
        daemon.shutdown()
        # Callback after shutdown must be a safe no-op
        daemon.audio_callback(indata, 1280, None, None)
