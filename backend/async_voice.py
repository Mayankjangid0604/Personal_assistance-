"""
Async Voice Pipeline for Aisha AI Assistant (Phase 2 Step 3).

Wraps the existing blocking voice.py module with async-safe interfaces
so that TTS and STT operations don't block the event loop.

Also emits voice state events to the EventBus so that WebSocket
clients (frontend Orb, mini window) receive real-time voice state.

Usage::

    from async_voice import async_speak, async_listen, get_voice_state

    # In an async handler:
    await async_speak("Hello, I'm Aisha!")
    text = await async_listen()
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from async_bridge import run_sync, event_bus

_log = logging.getLogger("aisha.async_voice")

# Current voice state — readable from anywhere
_voice_state: str = "idle"  # "idle" | "speaking" | "listening"


def get_voice_state() -> str:
    """Return the current voice pipeline state."""
    return _voice_state


async def async_speak(text: str) -> bool:
    """
    Speak text asynchronously without blocking the event loop.

    Emits voice state events:
        - ``voice:state`` → ``{"state": "speaking"}`` (start)
        - ``voice:state`` → ``{"state": "idle"}``     (done)

    Parameters
    ----------
    text : str
        The text to speak.

    Returns
    -------
    bool
        ``True`` if speech completed successfully, ``False`` on error.
    """
    global _voice_state

    if not text or not text.strip():
        return False

    _voice_state = "speaking"
    await event_bus.emit("voice:state", {"state": "speaking", "text": text[:80]})

    try:
        # Import here to avoid module-level pyttsx3 init
        from voice import speak
        result = await run_sync(speak, text)
        return result
    except Exception as e:
        _log.error("async_speak error: %s", e)
        return False
    finally:
        _voice_state = "idle"
        await event_bus.emit("voice:state", {"state": "idle"})


async def async_listen(
    timeout: int = 5,
    phrase_time_limit: int = 10,
    language: str = "en-IN",
) -> str | None:
    """
    Listen to the microphone asynchronously without blocking the event loop.

    Emits voice state events:
        - ``voice:state`` → ``{"state": "listening"}`` (start)
        - ``voice:state`` → ``{"state": "idle"}``      (done)

    Parameters
    ----------
    timeout : int
        Max seconds to wait for speech to start.
    phrase_time_limit : int
        Max seconds of speech to capture.
    language : str
        Language code for recognition.

    Returns
    -------
    str or None
        The recognised text, or ``None`` if nothing was understood.
    """
    global _voice_state

    _voice_state = "listening"
    await event_bus.emit("voice:state", {"state": "listening"})

    try:
        from voice import listen
        text = await run_sync(listen, timeout, phrase_time_limit, language)
        return text
    except Exception as e:
        _log.error("async_listen error: %s", e)
        return None
    finally:
        _voice_state = "idle"
        await event_bus.emit("voice:state", {"state": "idle"})


async def async_set_voice_rate(rate: int) -> None:
    """Change speaking speed asynchronously."""
    from voice import set_voice_rate
    await run_sync(set_voice_rate, rate)


async def async_set_voice_volume(volume: float) -> None:
    """Change volume asynchronously (0.0 to 1.0)."""
    from voice import set_voice_volume
    await run_sync(set_voice_volume, volume)


async def async_list_voices() -> list[dict[str, str]]:
    """Return available voices asynchronously."""
    from voice import list_voices
    return await run_sync(list_voices)


async def async_is_microphone_available() -> bool:
    """Check microphone availability asynchronously."""
    from voice import is_microphone_available
    return await run_sync(is_microphone_available)
