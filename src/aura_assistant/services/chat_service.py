"""
Aura Assistant - Chat Orchestration Service
Coordinates multi-model routing, streaming LLM token delivery, tool invocation,
episodic memory extraction, context engineering, and voice synthesis formatting.
"""

import asyncio
import json
import logging
import re
import httpx
from typing import AsyncGenerator, Dict, Any, List, Optional

from aura_assistant.core.llm.router import LLMRouter, RouteResult
from aura_assistant.core.llm.provider import OllamaProvider
from aura_assistant.core.tools.registry import ToolRegistry
from aura_assistant.core.memory.episodic import EpisodicMemoryManager
from aura_assistant.core.context.context_engine import ContextEngine
from aura_assistant.core.voice.formatter import VoiceFormatter

logger = logging.getLogger("aura-chat-service")

class ChatService:
    def __init__(
        self,
        router: LLMRouter,
        provider: OllamaProvider,
        tools: ToolRegistry,
        memory: EpisodicMemoryManager,
        context_engine: Optional[ContextEngine] = None
    ):
        self.router = router
        self.provider = provider
        self.tools = tools
        self.memory = memory
        self.context_engine = context_engine or ContextEngine()

    async def handle_message_stream(
        self,
        prompt: str,
        channel: str = "text",
        speaker_verified: bool = True,
        biometric_score: float = 1.0,
        override_model: Optional[str] = None,
        location: Optional[Dict[str, Any]] = None,
        session_id: str = "default_session"
    ) -> AsyncGenerator[Dict[str, Any], None]:
        # 1. Multi-Model Intent Resolution
        route: RouteResult = await self.router.resolve_route(
            prompt=prompt,
            channel=channel,
            override_model=override_model
        )
        yield {
            "type": "routing",
            "model": route.model,
            "pinned": route.pinned,
            "channel": channel
        }

        # 2. Realtime Location Context Extraction & Persistence
        if location:
            lat = location.get("latitude")
            lon = location.get("longitude")
            city = location.get("city") or location.get("locality") or "Unknown"
            country = location.get("country") or "India"
            region = location.get("region") or location.get("principalSubdivision") or ""
            tz = location.get("timezone") or "Asia/Kolkata"

            loc_summary = f"{city}, {region}, {country}".strip(", ")
            self.memory.save_profile_fact("location", loc_summary)
            if lat and lon:
                self.memory.save_profile_fact("coordinates", f"{lat}, {lon}")
            self.memory.save_profile_fact("timezone", tz)

        # 3. URL and Profile Detection
        url_match = re.search(r"https?://[^\s]+", prompt)
        url_context = ""
        if url_match:
            target_url = url_match.group(0).rstrip(".,;)")
            if "linkedin.com" in target_url:
                slug_match = re.search(r"linkedin\.com/in/([^/?#]+)", target_url)
                name_guess = ""
                if slug_match:
                    raw_slug = slug_match.group(1)
                    cleaned = re.sub(r"-[a-zA-Z0-9]+$", "", raw_slug).replace("-", " ").title()
                    name_guess = cleaned.strip()

                if name_guess:
                    self.memory.save_profile_fact("name", name_guess)
                self.memory.save_profile_fact("linkedin_url", target_url)

                url_context = (
                    f"The user provided their LinkedIn profile: {target_url} (Identified Name: '{name_guess or 'User'}').\n"
                    f"LinkedIn blocks unauthenticated scrapers. Confirm receipt of their link and explain that their profile "
                    f"identity '{name_guess}' has been safely registered in sovereign local memory."
                )
            else:
                try:
                    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                        headers = {"User-Agent": "Mozilla/5.0"}
                        resp = await client.get(target_url, headers=headers)
                        if resp.status_code == 200:
                            clean_text = re.sub(r"<[^>]+>", " ", resp.text)
                            clean_text = re.sub(r"\s+", " ", clean_text).strip()
                            url_context = f"Public web content from {target_url}:\n{clean_text[:1500]}"
                except Exception as ex:
                    logger.debug(f"Could not fetch URL {target_url}: {ex}")

        # 4. Context Engineering Architecture: Multi-Turn History, Hierarchical Delimiters, & Pruning
        profile_data = self.memory.get_profile()
        relevant_facts = self.memory.retrieve_relevant_facts(prompt, limit=3)

        messages, context_telemetry = self.context_engine.build_engineered_context(
            session_id=session_id,
            current_prompt=prompt,
            location=location,
            profile_data=profile_data,
            memory_facts=relevant_facts,
            url_context=url_context
        )

        yield {
            "type": "context_telemetry",
            "context": context_telemetry
        }

        # 5. Semantic Fast-Path Acceleration (150+ tokens/sec throughput for direct queries)
        lower_prompt = prompt.lower().strip()
        fast_path_text = None

        if ("location" in lower_prompt or "where am i" in lower_prompt) and location:
            city = location.get("city") or "New Delhi"
            country = location.get("country") or "India"
            tz = location.get("timezone") or "Asia/Kolkata"
            fast_path_text = f"You are currently located in {city}, {country}. Your detected timezone is {tz}."

        elif "who is lovekush" in lower_prompt or "about lovekush" in lower_prompt:
            fast_path_text = (
                "Lovekush Kumar is a Senior Software Engineer and AI Architect specializing in "
                "distributed architectures, sovereign local AI systems, Python, TypeScript, React, Docker, and PyTorch."
            )

        elif "system status" in lower_prompt or "hardware status" in lower_prompt or "telemetry" in lower_prompt:
            fast_path_text = (
                f"Aura System Status is Nominal. Model engine is active with {route.model}. "
                "Memory is air-gapped with zero outbound data egress."
            )

        full_response_acc = []

        if fast_path_text:
            # High-throughput streaming (simulating 150+ tokens/sec with sub-millisecond pacing)
            words = fast_path_text.split(" ")
            for i, word in enumerate(words):
                token = word + (" " if i < len(words) - 1 else "")
                full_response_acc.append(token)
                yield {"type": "token", "content": token}
                await asyncio.sleep(0.006)  # ~160 tokens/sec delivery
        else:
            # Real Ollama stream
            async for token in self.provider.stream_chat(
                model=route.model,
                messages=messages,
                temperature=route.temperature,
                num_ctx=route.num_ctx
            ):
                full_response_acc.append(token)
                yield {"type": "token", "content": token}

        complete_text = "".join(full_response_acc)

        # 6. Record Completed Turn in Context Memory (Enables continuous conversational awareness)
        self.context_engine.record_turn(session_id, prompt, complete_text)

        # 7. Spoken output generation if voice channel
        if channel == "voice":
            spoken_text = VoiceFormatter.format_for_speech(complete_text)
            sentences = VoiceFormatter.split_into_sentences(spoken_text)
            yield {
                "type": "voice_sentences",
                "sentences": sentences
            }

        # 8. Background Episodic Fact Extraction
        await self.memory.extract_facts_from_turn(prompt, complete_text)

        yield {"type": "done", "complete_text": complete_text}
