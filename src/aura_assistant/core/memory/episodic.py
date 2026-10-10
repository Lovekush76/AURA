"""
Aura Assistant - Episodic Memory Engine
Extracts user facts and preferences with strict length/count bounds, deduplication,
in-memory profile caching, diff-only atomic batch writes, and precomputed lexical tokens +
64-dim n-gram hash projections for sub-millisecond Reciprocal Rank Fusion (RRF) retrieval.
"""

import re
import math
import json
import hashlib
import logging
import datetime
import threading
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

logger = logging.getLogger("aura-episodic-memory")

MAX_FACT_CHARS = 220
MAX_TOTAL_FACTS = 250

STOP_WORDS = {
    "the", "is", "are", "was", "were", "a", "an", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "and", "or", "but", "what", "how", "why", "who",
    "where", "when", "can", "you", "me", "my", "i", "it", "this", "that"
}

QUESTION_PREFIXES = (
    "what ", "how ", "why ", "who ", "where ", "when ", "can you", "could you",
    "would you", "do you", "is there", "are there", "tell me "
)


def _normalize_fact_key(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().strip()).rstrip(".,;!")


def _sanitize_fact_text(raw_text: str, max_chars: int = MAX_FACT_CHARS) -> str:
    """
    Extracts a single clean sentence/line and bounds it to max_chars on word boundaries.
    Prevents multiline prompts or code blocks from being stored as one unbounded fact.
    """
    if not raw_text:
        return ""
    first_clause = re.split(r"[\r\n]+|(?<=[\.!])\s+", raw_text.strip())[0]
    clean = re.sub(r"\s+", " ", first_clause).strip()
    if len(clean) <= max_chars:
        return clean
    clipped = clean[:max_chars]
    last_space = clipped.rfind(" ")
    if last_space > max_chars // 2:
        clipped = clipped[:last_space]
    return clipped.rstrip(",;:") + "..."


def _is_valid_fact_candidate(text: str) -> bool:
    """Rejects questions, code blocks, or low-value fragments from being stored as facts."""
    clean = (text or "").strip()
    if len(clean) < 6 or "?" in clean or "```" in clean:
        return False
    lower = clean.lower()
    if lower.startswith(QUESTION_PREFIXES):
        return False
    return True


class EpisodicMemoryManager:
    def __init__(self, storage_dir: Path = Path("data/memory")):
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.facts_file = self.storage_dir / "facts.json"
        self.profile_file = self.storage_dir.parent / "profile" / "user_profile.json"
        self.profile_file.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._profile: Dict[str, Any] = self._load_profile_from_disk()
        self._facts: List[Dict[str, Any]] = self._load_facts_from_disk()

    @staticmethod
    def _tokenize_lexical(text: str) -> List[str]:
        return [t for t in re.findall(r"\w+", (text or "").lower()) if t not in STOP_WORDS]

    @staticmethod
    def _compute_fast_vector(text: str, dim: int = 64) -> List[float]:
        """
        Computes a normalized L2 64-dimensional character/word n-gram feature hash projection.
        Note: This is a deterministic locality-sensitive lexical/morphological hash vector
        for <0.1ms local RRF scoring alongside BM25, NOT a neural semantic embedding.
        """
        vec = [0.0] * dim
        clean = (text or "").lower().strip()
        tokens = [t for t in re.findall(r"\w+", clean) if t not in STOP_WORDS]
        features = tokens + [clean[i:i + 3] for i in range(max(0, len(clean) - 2))]
        if not features:
            return vec
        for feat in features:
            h = int(hashlib.md5(feat.encode("utf-8")).hexdigest()[:8], 16)
            idx = h % dim
            sign = 1.0 if (h >> 8) & 1 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [round(v / norm, 4) for v in vec]

    @staticmethod
    def _cosine_sim(v1: List[float], v2: List[float]) -> float:
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        return sum(a * b for a, b in zip(v1, v2))

    def _load_profile_from_disk(self) -> Dict[str, Any]:
        if self.profile_file.exists():
            try:
                data = json.loads(self.profile_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {}

    def _load_facts_from_disk(self) -> List[Dict[str, Any]]:
        if self.facts_file.exists():
            try:
                raw = json.loads(self.facts_file.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    enriched: List[Dict[str, Any]] = []
                    seen_norm = set()
                    for item in raw:
                        if not isinstance(item, dict):
                            continue
                        f_str = _sanitize_fact_text(str(item.get("fact", "")), MAX_FACT_CHARS)
                        if not f_str:
                            continue
                        norm_k = _normalize_fact_key(f_str)
                        if norm_k in seen_norm:
                            continue
                        seen_norm.add(norm_k)
                        item["fact"] = f_str
                        if "tokens" not in item or not isinstance(item["tokens"], list):
                            item["tokens"] = self._tokenize_lexical(f_str)
                        if "vector" not in item or not isinstance(item["vector"], list):
                            item["vector"] = self._compute_fast_vector(f_str)
                        enriched.append(item)
                    return self._enforce_fact_cap(enriched)
            except Exception:
                pass
        return []

    def _enforce_fact_cap(self, facts_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Bounds total fact count to MAX_TOTAL_FACTS, preserving profile facts and evicting oldest non-profile entries."""
        if len(facts_list) <= MAX_TOTAL_FACTS:
            return facts_list
        profile_facts = [f for f in facts_list if f.get("category") == "profile"]
        other_facts = [f for f in facts_list if f.get("category") != "profile"]
        keep_other = max(0, MAX_TOTAL_FACTS - len(profile_facts))
        return profile_facts + other_facts[-keep_other:]

    def get_profile(self) -> Dict[str, Any]:
        """Returns a defensive copy of the managed in-memory profile cache (0 disk I/O)."""
        with self._lock:
            return dict(self._profile)

    def update_profile_facts(
        self,
        updates: Dict[str, Any],
        persist_sync: bool = True
    ) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Normalizes and compares profile fields against the in-memory cache.
        Skips all disk/SQLite writes if no values changed.
        When changed, updates memory atomically and optionally persists in one batch.
        """
        if not updates:
            return False, []

        changed_orm_entries: List[Dict[str, Any]] = []
        now_iso = datetime.datetime.now().isoformat()

        with self._lock:
            changed = False
            for key, raw_val in updates.items():
                if raw_val is None:
                    continue
                val_str = _sanitize_fact_text(str(raw_val).strip(), max_chars=180)
                if not val_str:
                    continue
                existing_val = str(self._profile.get(key, "")).strip()
                if existing_val == val_str:
                    continue

                changed = True
                self._profile[key] = val_str
                fact_str = _sanitize_fact_text(f"User {key}: {val_str}", MAX_FACT_CHARS)
                prefix = f"User {key}:"
                self._facts = [
                    f for f in self._facts
                    if not str(f.get("fact", "")).startswith(prefix) and f.get("key") != key
                ]
                self._facts.append({
                    "category": "profile",
                    "key": key,
                    "fact": fact_str,
                    "source": "system",
                    "updated_at": now_iso,
                    "tokens": self._tokenize_lexical(fact_str),
                    "vector": self._compute_fast_vector(fact_str)
                })
                changed_orm_entries.append({
                    "kind": "profile",
                    "content": fact_str,
                    "importance": 1.5
                })

            if not changed:
                return False, []

            self._facts = self._enforce_fact_cap(self._facts)

        if persist_sync:
            self.flush_persistence_sync(changed_orm_entries, write_profile=True)

        return True, changed_orm_entries

    def save_profile_fact(self, key: str, value: Any, persist_sync: bool = True) -> bool:
        """Saves a single user profile attribute if changed."""
        changed, _ = self.update_profile_facts({key: value}, persist_sync=persist_sync)
        return changed

    def flush_persistence_sync(
        self,
        orm_entries: Optional[List[Dict[str, Any]]] = None,
        write_profile: bool = False
    ) -> None:
        """
        Thread-safe synchronous persistence helper that writes profile/facts JSON once
        and commits batch SQLite ORM rows in a single transaction.
        """
        try:
            with self._lock:
                profile_snapshot = dict(self._profile)
                facts_snapshot = list(self._facts)

            if write_profile:
                self.profile_file.write_text(json.dumps(profile_snapshot, indent=2), encoding="utf-8")
            self.facts_file.write_text(json.dumps(facts_snapshot, indent=2), encoding="utf-8")

            if orm_entries:
                from aura_assistant.core.db.session import persist_memories_batch_orm
                persist_memories_batch_orm(orm_entries)
        except Exception as e:
            logger.error(f"Failed to persist episodic memory batch: {e}")

    def archive_compacted_summary(
        self,
        session_id: str,
        summary_chunk: str,
        persist_sync: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Indexes a bounded compacted conversation summary into the episodic store."""
        clean_chunk = _sanitize_fact_text(summary_chunk, max_chars=MAX_FACT_CHARS - 32)
        if not clean_chunk:
            return None
        fact_str = _sanitize_fact_text(f"[Session {session_id} Archive] {clean_chunk}", MAX_FACT_CHARS)
        norm_target = _normalize_fact_key(fact_str)

        with self._lock:
            if any(_normalize_fact_key(f.get("fact", "")) == norm_target for f in self._facts):
                return None
            self._facts.append({
                "category": "episodic_archive",
                "key": f"archive_{session_id}_{len(self._facts)}",
                "fact": fact_str,
                "source": "compaction",
                "updated_at": datetime.datetime.now().isoformat(),
                "tokens": self._tokenize_lexical(fact_str),
                "vector": self._compute_fast_vector(fact_str)
            })
            self._facts = self._enforce_fact_cap(self._facts)

        orm_entry = {"kind": "episodic_archive", "content": fact_str, "importance": 1.2}
        if persist_sync:
            self.flush_persistence_sync([orm_entry], write_profile=False)
        return orm_entry

    async def extract_facts_from_turn(
        self,
        user_text: str,
        assistant_text: str,
        persist_sync: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Extracts bounded, non-question facts and profile attributes from user_text,
        deduplicates against existing facts, and batches persistence into a single write.
        """
        if not user_text or not user_text.strip():
            return []

        markers = [
            ("my name is", "identity", "name"),
            ("i prefer", "preference", "preference"),
            ("always use", "rule", "rule"),
            ("remember that", "fact", "custom_fact"),
            ("i work with", "context", "work_stack")
        ]

        lower_u = user_text.lower()
        now_iso = datetime.datetime.now().isoformat()
        orm_entries: List[Dict[str, Any]] = []
        facts_modified = False

        for phrase, category, key in markers:
            if phrase in lower_u:
                idx = lower_u.find(phrase)
                candidate = _sanitize_fact_text(user_text[idx:], MAX_FACT_CHARS)
                if not _is_valid_fact_candidate(candidate):
                    continue
                norm_cand = _normalize_fact_key(candidate)
                with self._lock:
                    if any(_normalize_fact_key(f.get("fact", "")) == norm_cand for f in self._facts):
                        continue
                    self._facts = [
                        f for f in self._facts
                        if _normalize_fact_key(f.get("fact", "")) != norm_cand
                        and not (key != "custom_fact" and f.get("key") == key)
                    ]
                    self._facts.append({
                        "category": category,
                        "key": key,
                        "fact": candidate,
                        "source": "conversation",
                        "updated_at": now_iso,
                        "tokens": self._tokenize_lexical(candidate),
                        "vector": self._compute_fast_vector(candidate)
                    })
                    self._facts = self._enforce_fact_cap(self._facts)
                    facts_modified = True
                orm_entries.append({"kind": category, "content": candidate, "importance": 1.1})
                logger.info(f"Upserted bounded episodic memory fact: '{candidate}'")

        patterns = {
            "headline": r"\bmy\s+(?:headline|title|role)\s+(?:is\s*)?[:\s]+([^\n\.,\?]+)",
            "about": r"\bmy\s+(?:bio|summary)\s+(?:is\s*)?[:\s]+([^\n\.\?]+)",
            "skills": r"\bmy\s+(?:skills?|tech stack|technologies)\s+(?:are|is)?[:\s]+([^\n\.\?]+)",
            "experience": r"\b(?:my\s+experience\s+is|i\s+work\s+at)\s*[:\s]*([^\n\.\?]+)",
            "education": r"\b(?:my\s+education\s+is|i\s+studied\s+at)\s*[:\s]*([^\n\.\?]+)",
            "location": r"\b(?:my\s+location\s+is|i\s+am\s+based\s+in|i\s+live\s+in)\s*[:\s]*([^\n\.\?]+)"
        }
        profile_updates: Dict[str, Any] = {}
        for key, pat in patterns.items():
            match = re.search(pat, user_text, re.IGNORECASE)
            if match:
                val = _sanitize_fact_text(match.group(1).strip(), max_chars=160)
                if len(val) > 2 and "?" not in val and _is_valid_fact_candidate(val):
                    profile_updates[key] = val

        profile_changed = False
        if profile_updates:
            profile_changed, prof_orm = self.update_profile_facts(profile_updates, persist_sync=False)
            if profile_changed:
                orm_entries.extend(prof_orm)

        if (facts_modified or profile_changed) and persist_sync:
            self.flush_persistence_sync(orm_entries, write_profile=profile_changed)

        return orm_entries

    def retrieve_relevant_facts(
        self,
        query: str,
        limit: int = 4,
        max_total_chars: int = 600
    ) -> List[str]:
        """
        Hybrid Retrieval using Reciprocal Rank Fusion (RRF):
        Combines precomputed BM25-style Lexical Specificity Scoring + 64-dim N-Gram Hash Cosine
        Similarity + Profile Authority Boost, capped by both item count and total character/token budget.
        """
        with self._lock:
            facts_snapshot = list(self._facts)

        if not facts_snapshot:
            return []

        q_tokens = self._tokenize_lexical(query)
        if not q_tokens:
            q_tokens = re.findall(r"\w+", (query or "").lower())
        q_vec = self._compute_fast_vector(query)

        bm25_scores: List[Tuple[int, float]] = []
        vec_scores: List[Tuple[int, float]] = []

        N = max(1, len(facts_snapshot))
        for idx, item in enumerate(facts_snapshot):
            f_text = item.get("fact", "")
            f_tokens = set(item.get("tokens") or self._tokenize_lexical(f_text))

            lex_score = 0.0
            for qt in q_tokens:
                if qt in f_tokens:
                    lex_score += 1.0 + (len(qt) * 0.15)
            bm25_scores.append((idx, lex_score))

            item_vec = item.get("vector") or self._compute_fast_vector(f_text)
            sim = self._cosine_sim(q_vec, item_vec)
            vec_scores.append((idx, sim))

        bm25_ranked = sorted(bm25_scores, key=lambda x: x[1], reverse=True)
        vec_ranked = sorted(vec_scores, key=lambda x: x[1], reverse=True)

        bm25_rank_map = {doc_idx: rank for rank, (doc_idx, _) in enumerate(bm25_ranked)}
        vec_rank_map = {doc_idx: rank for rank, (doc_idx, _) in enumerate(vec_ranked)}

        bm25_dict = dict(bm25_scores)
        vec_dict = dict(vec_scores)

        rrf_scored: List[Tuple[float, str]] = []
        for idx, item in enumerate(facts_snapshot):
            f_text = item.get("fact", "")
            lex_val = bm25_dict.get(idx, 0.0)
            sim_val = vec_dict.get(idx, 0.0)

            if lex_val == 0.0 and sim_val < 0.22:
                continue

            r_bm25 = bm25_rank_map.get(idx, N)
            r_vec = vec_rank_map.get(idx, N)
            rrf_score = (1.0 / (60.0 + r_bm25)) + (1.0 / (60.0 + r_vec))

            if item.get("source") == "system" or item.get("category") == "profile":
                rrf_score += 0.008

            rrf_scored.append((rrf_score, f_text))

        rrf_scored.sort(key=lambda x: x[0], reverse=True)
        seen = set()
        results: List[str] = []
        total_chars = 0
        for _, fact in rrf_scored:
            bounded_fact = _sanitize_fact_text(fact, MAX_FACT_CHARS)
            norm_f = _normalize_fact_key(bounded_fact)
            if norm_f not in seen:
                if total_chars + len(bounded_fact) > max_total_chars and results:
                    break
                seen.add(norm_f)
                results.append(bounded_fact)
                total_chars += len(bounded_fact)
            if len(results) >= limit:
                break
        return results
