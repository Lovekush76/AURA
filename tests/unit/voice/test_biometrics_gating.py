import pytest
from aura_assistant.core.voice.gating import BiometricGating
from aura_assistant.core.voice.formatter import VoiceFormatter

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
