"""
Aura Assistant - VRAM Residency Arbiter & Model Memory Manager
Enforces strict residency limits, keeps voice models permanently locked,
and serializes heavy model loading within the 24GB VRAM ceiling.
"""

import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("aura-residency-arbiter")

class VRAMArbiter:
    def __init__(
        self,
        vram_ceiling_mb: int = 24576,
        safety_headroom_mb: int = 1024,
        idle_heavy_timeout_seconds: int = 600
    ):
        self.vram_ceiling_mb = vram_ceiling_mb
        self.safety_headroom_mb = safety_headroom_mb
        self.idle_heavy_timeout_seconds = idle_heavy_timeout_seconds

        # Pinned baseline: Voice Router (3500MB) + Embedding (600MB)
        self.pinned_models: Dict[str, int] = {
            "qwen3.5:4b": 3500,
            "nomic-embed-text": 600
        }
        
        # Heavy model registry with estimated footprints
        self.heavy_models_budget: Dict[str, int] = {
            "qwen3-coder:30b": 19500,
            "deepseek-r1:14b": 9500
        }

        self.active_heavy_model: Optional[str] = None
        self.last_heavy_activity_ts: float = 0.0

    @property
    def baseline_vram_mb(self) -> int:
        return sum(self.pinned_models.values())

    @property
    def current_allocated_vram_mb(self) -> int:
        allocated = self.baseline_vram_mb
        if self.active_heavy_model:
            allocated += self.heavy_models_budget.get(self.active_heavy_model, 0)
        return allocated

    def can_load_model(self, model_name: str) -> bool:
        if model_name in self.pinned_models:
            return True
        budget = self.heavy_models_budget.get(model_name, 19500)
        total_required = self.baseline_vram_mb + budget + self.safety_headroom_mb
        return total_required <= self.vram_ceiling_mb

    def notify_model_requested(self, model_name: str) -> Optional[str]:
        """
        Returns the model name to evict if swapping is needed to stay under ceiling.
        Ensures voice model is NEVER returned for eviction.
        """
        now = time.time()
        if model_name in self.pinned_models:
            return None  # Pinned models are never evicted

        evicted = None
        if self.active_heavy_model and self.active_heavy_model != model_name:
            evicted = self.active_heavy_model
            logger.info(f"Arbitration: Evicting {evicted} to accommodate requested {model_name}")

        self.active_heavy_model = model_name
        self.last_heavy_activity_ts = now
        return evicted

    def check_idle_eviction(self) -> Optional[str]:
        """Checks if active heavy model has exceeded idle timeout."""
        if not self.active_heavy_model:
            return None
        now = time.time()
        if (now - self.last_heavy_activity_ts) > self.idle_heavy_timeout_seconds:
            evicted = self.active_heavy_model
            self.active_heavy_model = None
            logger.info(f"Idle timeout expired for {evicted}. Scheduling eviction.")
            return evicted
        return None

    def get_telemetry(self) -> Dict[str, Any]:
        return {
            "vram_ceiling_mb": self.vram_ceiling_mb,
            "allocated_mb": self.current_allocated_vram_mb,
            "free_headroom_mb": self.vram_ceiling_mb - self.current_allocated_vram_mb,
            "pinned_models": list(self.pinned_models.keys()),
            "active_heavy_model": self.active_heavy_model,
            "safe_headroom_met": (self.vram_ceiling_mb - self.current_allocated_vram_mb) >= self.safety_headroom_mb
        }
