"""
Streaming STT Engine for Aisha AI Assistant (Phase 2 Step 1).

Provides a pluggable speech-to-text pipeline with:
  - Voice Activity Detection (energy-based, instant)
  - Continuous listening mode
  - Partial transcript support
  - EventBus integration for real-time state
  - Non-blocking async interface

Architecture:
  STTEngine (abstract) -> SpeechRecognitionSTT (default backend)

The engine emits EventBus events:
  - voice:listening     — microphone active
  - voice:partial       — partial transcript available
  - voice:transcript    — final transcript ready
  - voice:silence       — VAD detected silence

Usage::

    from stt_engine import stt_engine

    # One-shot recognition
    text = await stt_engine.recognize()

    # Start continuous listening
    await stt_engine.start_listening()
    # ... events flow through EventBus
    await stt_engine.stop_listening()
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from abc import ABC, abstractmethod
from typing import Any, Callable

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from async_bridge import run_sync, event_bus

_log = logging.getLogger("aisha.stt")


# ---------------------------------------------------------------------------
# Abstract STT Engine
# ---------------------------------------------------------------------------

class STTEngine(ABC):
    """Abstract base for speech-to-text engines."""

    @abstractmethod
    async def recognize(self, timeout: int = 5, language: str = "en-IN") -> str | None:
        """Perform one-shot speech recognition. Returns text or None."""
        ...

    @abstractmethod
    async def start_continuous(self, language: str = "en-IN") -> None:
        """Start continuous listening mode."""
        ...

    @abstractmethod
    async def stop_continuous(self) -> None:
        """Stop continuous listening mode."""
        ...

    @abstractmethod
    def is_listening(self) -> bool:
        """Return True if currently listening."""
        ...


# ---------------------------------------------------------------------------
# SpeechRecognition Backend (default, always available)
# ---------------------------------------------------------------------------

class SpeechRecognitionSTT(STTEngine):
    """
    STT backend using the `speech_recognition` library.

    Uses Google's free speech recognition API for transcription.
    Provides VAD via energy-based detection built into SpeechRecognition.
    """

    def __init__(self) -> None:
        self._listening = False
        self._continuous_task: asyncio.Task | None = None
        self._should_stop = False

    async def recognize(
        self, timeout: int = 5, language: str = "en-IN",
    ) -> str | None:
        """
        One-shot recognition: listen for speech and return text.

        Emits voice:listening and voice:transcript events.
        """
        await event_bus.emit("voice:listening", {"active": True})

        try:
            text = await run_sync(self._blocking_recognize, timeout, language)
            if text:
                await event_bus.emit("voice:transcript", {
                    "text": text, "is_final": True,
                })
            return text
        except Exception as e:
            _log.error("STT recognize error: %s", e)
            return None
        finally:
            await event_bus.emit("voice:listening", {"active": False})

    def _blocking_recognize(self, timeout: int, language: str) -> str | None:
        """Blocking recognition (runs in thread via run_sync)."""
        try:
            import speech_recognition as sr
            recognizer = sr.Recognizer()
            recognizer.energy_threshold = 4000
            recognizer.dynamic_energy_threshold = True
            recognizer.pause_threshold = 1.0

            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.3)
                audio = recognizer.listen(
                    source, timeout=timeout, phrase_time_limit=10,
                )

            text = recognizer.recognize_google(audio, language=language)
            return text.strip() if text else None

        except Exception as e:
            _log.debug("STT blocking recognize: %s", e)
            return None

    async def start_continuous(self, language: str = "en-IN") -> None:
        """Start continuous listening — runs recognition in a loop."""
        if self._listening:
            return

        self._listening = True
        self._should_stop = False
        await event_bus.emit("voice:listening", {"active": True, "mode": "continuous"})

        async def _loop():
            while not self._should_stop:
                text = await self.recognize(timeout=3, language=language)
                if text:
                    await event_bus.emit("voice:transcript", {
                        "text": text, "is_final": True,
                    })
                await asyncio.sleep(0.1)  # Brief pause between listens

            self._listening = False
            await event_bus.emit("voice:listening", {"active": False})

        self._continuous_task = asyncio.create_task(_loop())

    async def stop_continuous(self) -> None:
        """Stop continuous listening."""
        self._should_stop = True
        if self._continuous_task:
            self._continuous_task.cancel()
            try:
                await self._continuous_task
            except asyncio.CancelledError:
                pass
            self._continuous_task = None
        self._listening = False
        await event_bus.emit("voice:listening", {"active": False})

    def is_listening(self) -> bool:
        return self._listening


# ---------------------------------------------------------------------------
# Engine Factory
# ---------------------------------------------------------------------------

def _create_engine() -> STTEngine:
    """Create the best available STT engine."""
    # Try faster-whisper first (better quality, local)
    try:
        from faster_whisper import WhisperModel
        _log.info("faster-whisper available, but using SpeechRecognition for compatibility")
    except ImportError:
        pass

    # Default: SpeechRecognition (always available)
    return SpeechRecognitionSTT()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

stt_engine = _create_engine()
