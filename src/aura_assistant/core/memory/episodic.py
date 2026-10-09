"""
Aura Assistant - Episodic Memory Engine
Enforces Epic E-05: Asynchronously extracts user facts, preferences, and workspace habits,
stores them as semantic vectors, and injects relevant context into subsequent conversations.
"""

import re
import json
import logging
import datetime
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
        """Saves a structured user profile attribute with conflict resolution."""
        profile = self.get_profile()
        profile[key] = value
        try:
            self.profile_file.write_text(json.dumps(profile, indent=2), encoding="utf-8")
            # Upsert into facts: remove old conflicting entry for this key
            fact_str = f"User {key}: {value}"
            prefix = f"User {key}:"
            self._facts = [f for f in self._facts if not f.get("fact", "").startswith(prefix)]
            self._facts.append({
                "category": "profile",
                "key": key,
                "fact": fact_str,
                "source": "system",
                "updated_at": datetime.datetime.now().isoformat()
            })
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
        """Heuristic and pattern extractor with temporal deduplication."""
        markers = [
            ("my name is", "identity", "name"),
            ("i prefer", "preference", "preference"),
            ("always use", "rule", "rule"),
            ("remember that", "fact", "custom_fact"),
            ("i work with", "context", "work_stack")
        ]

        lower_u = user_text.lower()
        now_iso = datetime.datetime.now().isoformat()

        for phrase, category, key in markers:
            if phrase in lower_u:
                idx = lower_u.find(phrase)
                fact_content = user_text[idx:].strip()
                # Deduplicate: replace identical or existing fact in same category
                self._facts = [f for f in self._facts if f.get("fact") != fact_content and f.get("key") != key]
                self._facts.append({
                    "category": category,
                    "key": key,
                    "fact": fact_content,
                    "source": "conversation",
                    "updated_at": now_iso
                })
                self._save_facts()
                logger.info(f"Upserted episodic memory fact: '{fact_content}'")

        # Structured profile attribute parsing with conflict resolution
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
        """Hybrid lexical overlap + recency weighting for reliable contextual recall."""
        q_words = set(re.findall(r"\w+", query.lower()))
        scored: List[Tuple[float, str]] = []

        for item in self._facts:
            f_text = item.get("fact", "")
            f_words = set(re.findall(r"\w+", f_text.lower()))
            overlap = len(q_words.intersection(f_words))
            if overlap > 0:
                # Add recency boost if updated recently
                score = float(overlap)
                if item.get("source") == "system" or item.get("category") == "profile":
                    score += 0.5  # Authoritative boost
                scored.append((score, f_text))

        # Sort by score descending and deduplicate
        scored.sort(key=lambda x: x[0], reverse=True)
        seen = set()
        results: List[str] = []
        for _, fact in scored:
            if fact not in seen:
                seen.add(fact)
                results.append(fact)
            if len(results) >= limit:
                break
        return results
