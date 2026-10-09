import httpx
import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel

logger = logging.getLogger("aura-llm-router")

class RouteResult(BaseModel):
    model: str
    num_ctx: int
    temperature: float
    pinned: bool

class LLMRouter:
    def __init__(self, ollama_host: str = "http://127.0.0.1:11434"):
        self.ollama_host = ollama_host
        self.slots = {
            "voice": {"model": "qwen3.5:4b", "ctx": 1536, "temp": 0.4, "pinned": True},
            "chat": {"model": "qwen2.5:0.5b", "ctx": 1024, "temp": 0.5, "pinned": True},
            "code": {"model": "qwen3-coder:30b", "ctx": 2048, "temp": 0.2, "pinned": False},
            "reasoning": {"model": "deepseek-r1:14b", "ctx": 2048, "temp": 0.5, "pinned": False}
        }
        self.current_heavy_model: Optional[str] = None
        self._cached_available_models: Optional[set] = None

    async def get_available_models(self) -> set:
        """Fetches models currently present in Ollama."""
        try:
            async with httpx.AsyncClient(base_url=self.ollama_host, timeout=5.0) as client:
                resp = await client.get("/api/tags")
                if resp.status_code == 200:
                    models = resp.json().get("models", [])
                    names = {m.get("name") for m in models if m.get("name")}
                    # Also include base names without :latest if applicable
                    normalized = set(names)
                    for n in names:
                        if ":latest" in n:
                            normalized.add(n.replace(":latest", ""))
                        else:
                            normalized.add(f"{n}:latest")
                    self._cached_available_models = normalized
                    return normalized
        except Exception as e:
            logger.debug(f"Could not fetch available models from Ollama: {e}")
        return self._cached_available_models or set()

    async def warm_pinned_models(self):
        """Pins the fast voice model into VRAM/RAM upon system startup."""
        voice_cfg = self.slots["voice"]
        logger.info(f"Locking primary voice model '{voice_cfg['model']}' into memory...")
        try:
            async with httpx.AsyncClient(base_url=self.ollama_host, timeout=10.0) as client:
                await client.post("/api/generate", json={
                    "model": voice_cfg["model"],
                    "keep_alive": -1
                })
                logger.info("Voice model successfully locked into memory.")
        except Exception as e:
            logger.info(f"Background pre-warm initiated: {e}")

    async def resolve_route(self, prompt: str, channel: str = "text", override_model: Optional[str] = None) -> RouteResult:
        available = await self.get_available_models()
        default_model = self.slots["voice"]["model"] if self.slots["voice"]["model"] in available or not available else "qwen3.5:4b"

        if override_model:
            model_to_use = override_model if (not available or override_model in available) else default_model
            return RouteResult(model=model_to_use, num_ctx=4096, temperature=0.7, pinned=False)

        # Modality enforcement: Voice channel must never experience cold model swaps
        if channel == "voice":
            cfg = self.slots["voice"]
            model_to_use = cfg["model"] if (not available or cfg["model"] in available) else default_model
            return RouteResult(model=model_to_use, num_ctx=cfg["ctx"], temperature=cfg["temp"], pinned=True)

        # Structural intent detection for coding
        code_markers = ["def ", "class ", "import ", "function(", "const ", "SELECT ", "curl ", "npm ", "```"]
        if any(marker in prompt for marker in code_markers) or "write a script" in prompt.lower():
            target = self.slots["code"]["model"]
            await self._ensure_heavy_residency(target)
            cfg = self.slots["code"]
            return RouteResult(model=target, num_ctx=cfg["ctx"], temperature=cfg["temp"], pinned=False)

        # Algorithmic reasoning detection
        if any(w in prompt.lower() for w in ["prove", "analyze complexity", "architect", "deep analysis"]):
            target = self.slots["reasoning"]["model"]
            await self._ensure_heavy_residency(target)
            cfg = self.slots["reasoning"]
            return RouteResult(model=target, num_ctx=cfg["ctx"], temperature=cfg["temp"], pinned=False)

        # Standard conversation fallback
        cfg = self.slots["chat"]
        return RouteResult(model=cfg["model"], num_ctx=cfg["ctx"], temperature=cfg["temp"], pinned=True)

    async def _ensure_heavy_residency(self, target_model: str):
        """
        Safely swaps heavy models without evicting the pinned voice model.
        """
        if self.current_heavy_model == target_model:
            return

        try:
            async with httpx.AsyncClient(base_url=self.ollama_host, timeout=30.0) as client:
                if self.current_heavy_model:
                    logger.info(f"Unloading idle heavy model: {self.current_heavy_model}")
                    await client.post("/api/generate", json={"model": self.current_heavy_model, "keep_alive": 0})

                logger.info(f"Pre-warming heavy slot model: {target_model}")
                await client.post("/api/generate", json={"model": target_model, "keep_alive": "10m"})
                self.current_heavy_model = target_model
        except Exception as e:
            logger.warning(f"Could not pre-warm heavy model {target_model}: {e}")
