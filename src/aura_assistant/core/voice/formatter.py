"""
Aura Assistant - Voice Output Formatter
Strips markdown, raw URLs, code fences, and LaTeX equations from LLM responses
to produce clean, high-density, conversational spoken English for Piper TTS.
"""

import re

class VoiceFormatter:
    @staticmethod
    def format_for_speech(text: str) -> str:
        if not text:
            return ""

        # 1. Replace code blocks with spoken summary
        clean = re.sub(r"```[a-zA-Z]*\n[\s\S]*?\n```", " [code block emitted] ", text)
        clean = re.sub(r"`([^`]+)`", r"\1", clean)

        # 2. Strip Markdown links [text](url) -> text
        clean = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", clean)

        # 3. Strip raw URLs
        clean = re.sub(r"https?://\S+", "link", clean)

        # 4. Strip Markdown headers and bold/italics
        clean = re.sub(r"^#{1,6}\s+", "", clean, flags=re.MULTILINE)
        clean = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", clean)

        # 5. Strip Markdown list bullets
        clean = re.sub(r"^\s*[-*+]\s+", "", clean, flags=re.MULTILINE)
        clean = re.sub(r"^\s*\d+\.\s+", "", clean, flags=re.MULTILINE)

        # 6. Simplify LaTeX equations $...$ or $$...$$
        clean = re.sub(r"\$\$[\s\S]*?\$\$", "equation", clean)
        clean = re.sub(r"\$([^$]+)\$", r"\1", clean)

        # 7. Collapse whitespace and normalize punctuation
        clean = re.sub(r"\s+", " ", clean).strip()

        return clean

    @staticmethod
    def split_into_sentences(text: str) -> list[str]:
        """Splits paragraph into spoken sentence chunks for low-latency streaming TTS."""
        if not text:
            return []
        # Match sentence boundaries ending in . ! ? while preserving context
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        return [s.strip() for s in sentences if s.strip()]
