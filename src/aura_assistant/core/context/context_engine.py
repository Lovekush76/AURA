"""
Aura Assistant - Sovereign Context Engineering Engine
Handles multi-turn conversational history budgets, sliding window pruning,
hierarchical context layering, and real-time sensory fact injection.
"""

import json
import logging
import datetime
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger("aura-context-engine")

@dataclass
class ConversationTurn:
    role: str
    content: str
    timestamp: str = field(default_factory=lambda: datetime.datetime.now().strftime("%H:%M:%S"))
    token_est: int = 0

    def __post_init__(self):
        if not self.token_est:
            self.token_est = max(1, len(self.content) // 4)

@dataclass
class ContextBudget:
    max_context_tokens: int = 1536
    reserve_generation_tokens: int = 256
    system_reserve: int = 350
    history_budget: int = 800

class ContextEngine:
    """
    Production Context Engineering Engine.
    Structures system prompts with XML boundaries, maintains multi-turn session
    history, prunes context dynamically to avoid context overflow, and provides
    fast-path acceleration.
    """

    def __init__(self, budget: Optional[ContextBudget] = None):
        self.budget = budget or ContextBudget()
        self.session_histories: Dict[str, List[ConversationTurn]] = {}

    def get_or_create_history(self, session_id: str) -> List[ConversationTurn]:
        if session_id not in self.session_histories:
            self.session_histories[session_id] = []
        return self.session_histories[session_id]

    def record_turn(self, session_id: str, user_prompt: str, assistant_response: str):
        """Records a completed turn in session memory."""
        history = self.get_or_create_history(session_id)
        history.append(ConversationTurn(role="user", content=user_prompt))
        history.append(ConversationTurn(role="assistant", content=assistant_response))
        # Keep maximum 20 turns in memory
        if len(history) > 40:
            self.session_histories[session_id] = history[-40:]

    def build_engineered_context(
        self,
        session_id: str,
        current_prompt: str,
        location: Optional[Dict[str, Any]] = None,
        profile_data: Optional[Dict[str, Any]] = None,
        memory_facts: Optional[List[str]] = None,
        url_context: Optional[str] = None
    ) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
        """
        Assembles hierarchically layered context with XML delimiters,
        sliding-window history pruning, and token telemetry.
        """
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. Layer 1: Core System Identity
        system_blocks = [
            "<identity>\n"
            "You are Aura, an advanced sovereign AI assistant and developer workspace.\n"
            "You run 100% locally on the user's host machine. Answer directly, concisely, and accurately without boilerplate fluff.\n"
            "</identity>"
        ]

        # 2. Layer 2: Real-time Location & Sensory Telemetry
        if location:
            city = location.get("city") or location.get("locality") or "Unknown"
            country = location.get("country") or "India"
            region = location.get("region") or location.get("principalSubdivision") or ""
            lat = location.get("latitude")
            lon = location.get("longitude")
            tz = location.get("timezone") or "Asia/Kolkata"

            loc_summary = f"{city}, {region}, {country}".strip(", ")
            system_blocks.append(
                f"<sensory_telemetry>\n"
                f"Current Timestamp: {now_str}\n"
                f"User Physical Location: {loc_summary}\n"
                f"Coordinates: {lat}, {lon}\n"
                f"Timezone: {tz}\n"
                f"Directive: Use this exact real-time location to answer all weather, local, time, and spatial questions.\n"
                f"</sensory_telemetry>"
            )

        # 3. Layer 3: Sovereign User Profile & Verified Facts
        if profile_data:
            profile_json = json.dumps(profile_data, indent=2)
            system_blocks.append(
                f"<user_profile>\n"
                f"{profile_json}\n"
                f"</user_profile>"
            )

        # 4. Layer 4: Retrieved Semantic Facts
        if memory_facts:
            facts_text = "\n".join(f"- {f}" for f in memory_facts)
            system_blocks.append(
                f"<episodic_memory>\n"
                f"{facts_text}\n"
                f"</episodic_memory>"
            )

        system_prompt = "\n\n".join(system_blocks)
        system_tokens_est = len(system_prompt) // 4

        # 5. Layer 5: Multi-Turn Conversation History with Budget Pruning
        history = self.get_or_create_history(session_id)
        included_turns: List[ConversationTurn] = []
        accumulated_history_tokens = 0

        # Traverse backwards from most recent turns to fit history budget
        for turn in reversed(history):
            if accumulated_history_tokens + turn.token_est > self.budget.history_budget:
                break
            included_turns.insert(0, turn)
            accumulated_history_tokens += turn.token_est

        # 6. Layer 6: User Query Augmentation
        augmented_user_content = current_prompt
        if url_context:
            augmented_user_content = f"{current_prompt}\n\n<external_context>\n{url_context}\n</external_context>"

        # Assembled OpenAI/Ollama compliant messages list
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ]

        for turn in included_turns:
            messages.append({"role": turn.role, "content": turn.content})

        messages.append({"role": "user", "content": augmented_user_content})

        total_context_tokens = system_tokens_est + accumulated_history_tokens + (len(augmented_user_content) // 4)

        telemetry = {
            "engineered": True,
            "system_tokens": system_tokens_est,
            "history_turns_included": len(included_turns),
            "history_tokens": accumulated_history_tokens,
            "total_context_tokens": total_context_tokens,
            "max_context_budget": self.budget.max_context_tokens,
            "memory_facts_count": len(memory_facts or []),
            "has_location_context": bool(location)
        }

        return messages, telemetry
