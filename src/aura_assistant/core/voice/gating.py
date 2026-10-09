"""
Aura Assistant - Biometric Sensitivity Gating
Enforces FR-VCE-03: Filters executable tools based on biometric speaker verification score.
Strikes 'personal' and 'critical' tools if verification score < 0.85.
"""

import logging
from typing import List, Dict, Any, Set

logger = logging.getLogger("aura-voice-gating")

BIOMETRIC_THRESHOLD = 0.85

class BiometricGating:
    def __init__(self, tools_config: Dict[str, Any]):
        self.tools_config = tools_config.get("tools", {})

    def filter_allowed_tools(
        self,
        available_tool_names: List[str],
        speaker_verified: bool,
        biometric_score: float = 1.0,
        channel: str = "text"
    ) -> List[str]:
        """
        Filters tools according to biometric clearance.
        Voice queries without confirmed speaker match (score < 0.85)
        are restricted to 'public' sensitivity tools only.
        """
        # Text/Authenticated API channels bypass voice biometric gate if token is valid
        if channel != "voice":
            return available_tool_names

        is_authorized = speaker_verified and (biometric_score >= BIOMETRIC_THRESHOLD)
        if is_authorized:
            return available_tool_names

        logger.warning(
            f"Voice Biometric Gating Active: score={biometric_score:.2f} (< {BIOMETRIC_THRESHOLD}). "
            f"Restricting tool privileges."
        )

        allowed: List[str] = []
        for name in available_tool_names:
            tool_spec = self.tools_config.get(name, {})
            sensitivity = tool_spec.get("sensitivity", "personal")
            requires_voice_match = tool_spec.get("requires_voice_match", True)

            if not requires_voice_match or sensitivity == "public":
                allowed.append(name)
            else:
                logger.info(f"Stripped sensitive tool '{name}' due to lack of biometric match.")

        return allowed
