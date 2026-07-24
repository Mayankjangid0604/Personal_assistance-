"""
Streaming TTS Engine for Aisha AI Assistant (Phase 2 Step 2).

Provides interruptible, chunked text-to-speech with:
  - Sentence-level splitting for fast first-word latency
  - Async playback queue (non-blocking)
  - Interruption support (stop mid-sentence)
  - EventBus integration for orb/voice state sync
  - Pluggable backend architecture

Architecture:
  TTSEngine (abstract) -> Pyttsx3TTS (default backend)

EventBus events:
  - voice:speaking      — TTS started
  - voice:playback_start — audio chunk playing
  - voice:playback_end  — audio chunk finished
  - voice:interrupted   — playback interrupted
  - voice:idle          — TTS queue empty

Usage::

    from tts_engine import tts_engine

    # Speak with interruption support
    await tts_engine.speak("Hello! How are you today?")

    # Interrupt current speech
    await tts_engine.interrupt()

    # Check state
    if tts_engine.is_speaking():
        await tts_engine.interrupt()
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from abc import ABC, abstractmethod
from collections import deque
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from async_bridge import run_sync, event_bus

_log = logging.getLogger("aisha.tts")


# ---------------------------------------------------------------------------
# Sentence Splitter
# ---------------------------------------------------------------------------

def split_into_chunks(text: str, max_chunk_len: int = 200) -> list[str]:
    """
    Split text into sentence-level chunks for streaming playback.

    This enables:
    1. Fast first-word latency (start speaking first sentence immediately)
    2. Clean interruption points (between sentences)
    3. Natural speech rhythm
    """
    # Split on sentence boundaries
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())

    chunks = []
    current = ""

    for sentence in sentences:
        if not sentence.strip():
            continue
        if len(current) + len(sentence) > max_chunk_len and current:
            chunks.append(current.strip())
            current = sentence
        else:
            current += (" " if current else "") + sentence

    if current.strip():
        chunks.append(current.strip())

    return chunks if chunks else [text.strip()]


# ---------------------------------------------------------------------------
# Abstract TTS Engine
# ---------------------------------------------------------------------------

class TTSEngine(ABC):
    """Abstract base for text-to-speech engines."""

    @abstractmethod
    async def speak(self, text: str) -> bool:
        """Speak text, returning True on success."""
        ...

    @abstractmethod
    async def speak_streamed(self, text: str) -> bool:
        """Speak text in chunks with interruption support."""
        ...

    @abstractmethod
    async def interrupt(self) -> None:
        """Stop current speech immediately."""
        ...

    @abstractmethod
    def is_speaking(self) -> bool:
        """Return True if currently speaking."""
        ...


# ---------------------------------------------------------------------------
# Pyttsx3 Backend (default, always available)
# ---------------------------------------------------------------------------

class Pyttsx3TTS(TTSEngine):
    """
    TTS backend using pyttsx3 (Windows SAPI5 / espeak).

    Provides sentence-level chunking for interruptibility.
    Each chunk runs in a thread via run_sync to avoid blocking.
    """

    def __init__(self) -> None:
        self._speaking = False
        self._interrupted = False
        self._speak_task: asyncio.Task | None = None

    async def speak(self, text: str) -> bool:
        """Speak text (single chunk, blocking until done)."""
        if not text or not text.strip():
            return False

        self._speaking = True
        self._interrupted = False
        await event_bus.emit("voice:speaking", {"text": text[:80]})

        try:
            result = await run_sync(self._blocking_speak, text)
            return result
        except Exception as e:
            _log.error("TTS speak error: %s", e)
            return False
        finally:
            self._speaking = False
            if not self._interrupted:
                await event_bus.emit("voice:idle", {})

    async def speak_streamed(self, text: str) -> bool:
        """
        Speak text in sentence-level chunks.

        Checks for interruption between each chunk.
        Emits playback_start/playback_end for each chunk.
        """
        if not text or not text.strip():
            return False

        chunks = split_into_chunks(text)
        self._speaking = True
        self._interrupted = False
        await event_bus.emit("voice:speaking", {
            "text": text[:80],
            "chunks": len(chunks),
        })

        try:
            for i, chunk in enumerate(chunks):
                if self._interrupted:
                    await event_bus.emit("voice:interrupted", {
                        "at_chunk": i,
                        "total_chunks": len(chunks),
                    })
                    return False

                await event_bus.emit("voice:playback_start", {
                    "chunk": i,
                    "total": len(chunks),
                    "text": chunk[:60],
                })

                await run_sync(self._blocking_speak, chunk)

                await event_bus.emit("voice:playback_end", {
                    "chunk": i,
                    "total": len(chunks),
                })

                # Brief pause between sentences for natural rhythm
                if i < len(chunks) - 1:
                    await asyncio.sleep(0.05)

            return True

        except Exception as e:
            _log.error("TTS streamed speak error: %s", e)
            return False
        finally:
            self._speaking = False
            await event_bus.emit("voice:idle", {})

    def _blocking_speak(self, text: str) -> bool:
        """Blocking TTS call (runs in thread)."""
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", 175)
            engine.setProperty("volume", 1.0)

            # Try female voice
            voices = engine.getProperty("voices")
            for v in voices:
                if "female" in v.name.lower() or "zira" in v.name.lower():
                    engine.setProperty("voice", v.id)
                    break

            engine.say(text)
            engine.runAndWait()
            engine.stop()
            return True
        except Exception as e:
            _log.error("Pyttsx3 blocking speak: %s", e)
            return False

    async def interrupt(self) -> None:
        """Signal interruption — current chunk finishes, no more chunks play."""
        self._interrupted = True
        self._speaking = False
        await event_bus.emit("voice:interrupted", {})

        # Try to stop pyttsx3 engine
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.stop()
        except Exception:
            pass

    def is_speaking(self) -> bool:
        return self._speaking


# ---------------------------------------------------------------------------
# Engine Factory
# ---------------------------------------------------------------------------

def _create_engine() -> TTSEngine:
    """Create the best available TTS engine."""
    # Default: pyttsx3 (always available on Windows)
    return Pyttsx3TTS()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

tts_engine = _create_engine()
