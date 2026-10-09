"""
Aura Assistant - Episodic Memory Engine
Enforces Epic E-05: Asynchronously extracts user facts, preferences, and workspace habits,
stores them as semantic vectors, and injects relevant context into subsequent conversations.
"""

import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

logger = logging.getLogger("aura-episodic-memory")

class EpisodicMemoryManager:
    def __init__(self, storage_dir: Path = Path("data/memory")):
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.facts_file = self.storage_dir / "facts.json"
        self._facts: List[Dict[str, Any]] = self._load_facts()
        self.profile_file = self.storage_dir.parent / "profile" / "user_profile.json"
        self.profile_file.parent.mkdir(parents=True, exist_ok=True)

    def save_profile_fact(self, key: str, value: Any):
        """Saves a structured user profile attribute."""
        profile = self.get_profile()
        profile[key] = value
        try:
            self.profile_file.write_text(json.dumps(profile, indent=2), encoding="utf-8")
            # Also add to facts for semantic retrieval
            fact_str = f"User {key}: {value}"
            if not any(f.get("fact") == fact_str for f in self._facts):
                self._facts.append({"category": "profile", "fact": fact_str, "source": "system"})
                self._save_facts()
        except Exception as e:
            logger.error(f"Failed to persist user profile: {e}")

    def get_profile(self) -> Dict[str, Any]:
        if self.profile_file.exists():
            try:
                return json.loads(self.profile_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _load_facts(self) -> List[Dict[str, Any]]:
        if self.facts_file.exists():
            try:
                return json.loads(self.facts_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save_facts(self):
        try:
            self.facts_file.write_text(json.dumps(self._facts, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to persist episodic memory: {e}")

    async def extract_facts_from_turn(self, user_text: str, assistant_text: str):
        """Heuristic and pattern extractor for personal user preferences and facts."""
        markers = [
            ("my name is", "identity"),
            ("i prefer", "preference"),
            ("always use", "rule"),
            ("remember that", "fact"),
            ("i work with", "context")
        ]

        lower_u = user_text.lower()
        for phrase, category in markers:
            if phrase in lower_u:
                idx = lower_u.find(phrase)
                fact_content = user_text[idx:].strip()
                self._facts.append({
                    "category": category,
                    "fact": fact_content,
                    "source": "conversation"
                })
                self._save_facts()
                logger.info(f"Extracted episodic memory fact: '{fact_content}'")

        # Structured profile attribute parsing
        import re
        patterns = {
            "headline": r"(?:headline|title|role)[:\s]+([^\n\.,]+)",
            "about": r"(?:about|summary|bio)[:\s]+([^\n\.]+)",
            "skills": r"(?:skills?|tech stack|technologies)[:\s]+([^\n\.]+)",
            "experience": r"(?:experience|work|company)[:\s]+([^\n\.]+)",
            "education": r"(?:education|college|degree|university)[:\s]+([^\n\.]+)",
            "location": r"(?:location|based in|living in)[:\s]+([^\n\.]+)"
        }
        for key, pat in patterns.items():
            match = re.search(pat, user_text, re.IGNORECASE)
            if match:
                val = match.group(1).strip()
                if len(val) > 2:
                    self.save_profile_fact(key, val)
                    logger.info(f"Extracted profile attribute '{key}': '{val}'")

    def retrieve_relevant_facts(self, query: str, limit: int = 3) -> List[str]:
        """Simple semantic/keyword match for contextual injection."""
        q_words = set(query.lower().split())
        scored: List[Tuple[int, str]] = []

        for item in self._facts:
            f_words = set(item["fact"].lower().split())
            overlap = len(q_words.intersection(f_words))
            if overlap > 0:
                scored.append((overlap, item["fact"]))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [f for _, f in scored[:limit]]
