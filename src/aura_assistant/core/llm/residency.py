"""
Aura Assistant - VRAM Residency Arbiter & Model Memory Manager
Enforces strict residency limits using measured model weight + KV-cache footprints,
queries runtime residency (/api/ps) and hardware telemetry when available,
keeps voice models permanently locked, and serializes heavy model loading.
"""

import shutil
import subprocess
import time
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("aura-residency-arbiter")

BYTES_PER_MIB = 1024 * 1024


def detect_gpu_vram_mib() -> Optional[ Dict[str, int] ]:
    """Queries nvidia-smi for actual total/free/used GPU memory in MiB if an NVIDIA GPU is present."""
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return None
    try:
        res = subprocess.run(
            [nvidia_smi, "--query-gpu=memory.total,memory.free,memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=2.0
        )
        if res.returncode == 0 and res.stdout.strip():
            first_line = res.stdout.strip().splitlines()[0]
            parts = [int(p.strip()) for p in first_line.split(",")]
            if len(parts) >= 3:
                return {"total_mib": parts[0], "free_mib": parts[1], "used_mib": parts[2]}
    except Exception as e:
        logger.debug(f"Could not query nvidia-smi: {e}")
    return None


class VRAMArbiter:
    def __init__(
        self,
        vram_ceiling_mb: int = 24576,
        safety_headroom_mb: int = 1024,
        idle_heavy_timeout_seconds: int = 600,
        voice_asr_overhead_mb: int = 0
    ):
        self.vram_ceiling_mb = vram_ceiling_mb
        self.safety_headroom_mb = safety_headroom_mb
        self.idle_heavy_timeout_seconds = idle_heavy_timeout_seconds
        self.voice_asr_overhead_mb = voice_asr_overhead_mb

        # Pinned baseline models (weights in MiB; qwen3.5:4b Q4_K_M ~2800 MiB, qwen2.5:0.5b ~465 MiB)
        # Note: nomic-embed-text (~275 MiB) is NOT pinned by default unless actively loaded in /api/ps.
        self.pinned_models: Dict[str, int] = {
            "qwen3.5:4b": 2800,
            "qwen2.5:0.5b": 465
        }

        # Base weight footprints (MiB) before KV cache
        self.model_weights_mib: Dict[str, int] = {
            "qwen2.5:0.5b": 465,
            "qwen2.5:1.5b": 1100,
            "qwen3.5:4b": 2800,
            "nomic-embed-text": 275,
            "deepseek-r1:14b": 9000,
            "qwen3-coder:30b": 17500
        }

        # Approximate KV-cache cost in MiB per 1,024 tokens of num_ctx (with FlashAttention + quantized KV)
        self.kv_mib_per_1k_ctx: Dict[str, float] = {
            "qwen2.5:0.5b": 12.0,
            "qwen2.5:1.5b": 18.0,
            "qwen3.5:4b": 28.0,
            "nomic-embed-text": 8.0,
            "deepseek-r1:14b": 38.0,
            "qwen3-coder:30b": 48.0
        }

        self.active_heavy_model: Optional[str] = None
        self.active_heavy_footprint_mib: int = 0
        self.last_heavy_activity_ts: float = 0.0
        self.last_runtime_ps: List[Dict[str, Any]] = []

    def estimate_model_memory_mb(self, model_name: str, num_ctx: int = 4096) -> int:
        """
        Estimates total memory (weights + KV cache for num_ctx with parallel=1) in MiB.
        """
        base_name = model_name[:-7] if model_name.endswith(":latest") else model_name
        weights = self.model_weights_mib.get(base_name, 17500)
        kv_rate = self.kv_mib_per_1k_ctx.get(base_name, 45.0)
        kv_mib = int((max(512, num_ctx) / 1024.0) * kv_rate)
        return weights + kv_mib

    def update_from_runtime_ps(self, ps_models: List[Dict[str, Any]]) -> None:
        """Updates arbiter state from Ollama /api/ps runtime payload."""
        self.last_runtime_ps = list(ps_models or [])
        loaded_names = set()
        for m in self.last_runtime_ps:
            name = m.get("name") or m.get("model") or ""
            if name.endswith(":latest"):
                loaded_names.add(name[:-7])
            loaded_names.add(name)

        if self.active_heavy_model and self.active_heavy_model not in loaded_names:
            # Confirmed unloaded from runtime
            self.active_heavy_model = None
            self.active_heavy_footprint_mib = 0

    @property
    def baseline_vram_mb(self) -> int:
        # Pinned models + optional GPU voice ASR overhead
        return sum(self.pinned_models.values()) + self.voice_asr_overhead_mb

    @property
    def current_allocated_vram_mb(self) -> int:
        if self.last_runtime_ps:
            measured_bytes = sum(int(m.get("size_vram") or m.get("size") or 0) for m in self.last_runtime_ps)
            if measured_bytes > 0:
                return max(self.baseline_vram_mb, measured_bytes // BYTES_PER_MIB)
        allocated = self.baseline_vram_mb
        if self.active_heavy_model:
            allocated += (
                self.active_heavy_footprint_mib
                or self.estimate_model_memory_mb(self.active_heavy_model, 32768)
            )
        return allocated

    def can_load_model(self, model_name: str, num_ctx: int = 32768) -> bool:
        base_name = model_name[:-7] if model_name.endswith(":latest") else model_name
        if base_name in self.pinned_models:
            return True
        candidate_mib = self.estimate_model_memory_mb(base_name, num_ctx)
        total_required = self.baseline_vram_mb + candidate_mib + self.safety_headroom_mb
        return total_required <= self.vram_ceiling_mb

    def notify_model_requested(self, model_name: str, num_ctx: int = 32768) -> Optional[str]:
        """
        Returns the heavy model name to evict if swapping is needed to stay under ceiling.
        Ensures pinned voice/chat models are NEVER returned for eviction.
        """
        now = time.time()
        base_name = model_name[:-7] if model_name.endswith(":latest") else model_name
        if base_name in self.pinned_models:
            return None

        evicted = None
        if self.active_heavy_model and self.active_heavy_model != model_name:
            evicted = self.active_heavy_model
            logger.info(f"Arbitration: Evicting {evicted} to accommodate requested {model_name}")

        self.active_heavy_model = model_name
        self.active_heavy_footprint_mib = self.estimate_model_memory_mb(base_name, num_ctx)
        self.last_heavy_activity_ts = now
        return evicted

    def confirm_model_unloaded(self, model_name: str) -> None:
        """Marks a model's memory as freed only after unload is confirmed."""
        if self.active_heavy_model == model_name:
            self.active_heavy_model = None
            self.active_heavy_footprint_mib = 0

    def check_idle_eviction(self) -> Optional[str]:
        """Checks if active heavy model has exceeded idle timeout."""
        if not self.active_heavy_model:
            return None
        now = time.time()
        if (now - self.last_heavy_activity_ts) > self.idle_heavy_timeout_seconds:
            evicted = self.active_heavy_model
            self.active_heavy_model = None
            self.active_heavy_footprint_mib = 0
            logger.info(f"Idle timeout expired for {evicted}. Scheduling eviction.")
            return evicted
        return None

    def get_telemetry(self) -> Dict[str, Any]:
        gpu_hw = detect_gpu_vram_mib()
        allocated = self.current_allocated_vram_mb
        return {
            "vram_ceiling_mb": self.vram_ceiling_mb,
            "allocated_mb": allocated,
            "free_headroom_mb": max(0, self.vram_ceiling_mb - allocated),
            "pinned_models": list(self.pinned_models.keys()),
            "active_heavy_model": self.active_heavy_model,
            "safe_headroom_met": (self.vram_ceiling_mb - allocated) >= self.safety_headroom_mb,
            "runtime_loaded_models": [
                {
                    "name": m.get("name"),
                    "size_mib": int(m.get("size", 0)) // BYTES_PER_MIB,
                    "size_vram_mib": int(m.get("size_vram", 0)) // BYTES_PER_MIB,
                    "context_length": m.get("context_length")
                }
                for m in self.last_runtime_ps
            ],
            "hardware_gpu_mib": gpu_hw
        }
