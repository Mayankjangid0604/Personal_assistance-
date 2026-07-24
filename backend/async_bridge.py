"""
Async Bridge for Aisha AI Assistant.

Provides utilities for the gradual sync → async migration:

1. **run_sync(fn, *args)** — Run a blocking function off the event loop
   using ``asyncio.to_thread()``.  Wraps with error handling and logging.

2. **EventBus** — Lightweight async pub/sub for internal real-time events.
   Foundation for WebSocket broadcasting (Step 2), Orb sync (Step 4),
   and voice state changes (Step 3).

Usage::

    from async_bridge import run_sync, event_bus

    # In an async route handler:
    result = await run_sync(process_input, user_message)

    # Publish an event:
    await event_bus.emit("orb:state", {"state": "thinking"})

    # Subscribe to events (e.g. in a WebSocket handler):
    async for data in event_bus.subscribe("orb:state"):
        await ws.send_json(data)
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, AsyncIterator, Callable, TypeVar

_log = logging.getLogger("aisha.async_bridge")

T = TypeVar("T")


# ---------------------------------------------------------------------------
# run_sync — thread-safe bridge for blocking calls
# ---------------------------------------------------------------------------

async def run_sync(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """
    Run a synchronous (blocking) function in a separate thread.

    This is the standard pattern for calling sync code from an async
    context without blocking the event loop.  All brain pipeline,
    skill, memory, and database calls should go through this.

    Parameters
    ----------
    fn : callable
        The synchronous function to call.
    *args, **kwargs
        Arguments forwarded to *fn*.

    Returns
    -------
    T
        Whatever *fn* returns.

    Raises
    ------
    Exception
        Re-raises any exception from *fn* after logging.
    """
    try:
        if kwargs:
            # asyncio.to_thread doesn't support kwargs directly,
            # so we wrap in a lambda
            return await asyncio.to_thread(lambda: fn(*args, **kwargs))
        return await asyncio.to_thread(fn, *args)
    except Exception as exc:
        _log.error("run_sync(%s) raised: %s", fn.__name__, exc)
        raise


# ---------------------------------------------------------------------------
# get_event_loop — safe accessor
# ---------------------------------------------------------------------------

def get_event_loop() -> asyncio.AbstractEventLoop:
    """
    Return the running event loop, or create a new one if none exists.

    Useful for scheduling callbacks from non-async code (e.g. background
    threads that need to push events into the async world).
    """
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


# ---------------------------------------------------------------------------
# EventBus — async pub/sub for real-time internal events
# ---------------------------------------------------------------------------

class EventBus:
    """
    Lightweight async publish/subscribe event bus.

    Events are string-named channels.  Subscribers receive an
    ``asyncio.Queue`` and can iterate over it asynchronously.

    Thread-safe for emitting from sync background threads via
    ``emit_sync()``.

    Supported event names (convention, not enforced)::

        "orb:state"       — orb animation state changes
        "voice:state"     — voice pipeline state (listening/speaking/idle)
        "chat:typing"     — typing indicator
        "chat:response"   — new response chunk
        "system:status"   — health/status updates

    Usage::

        bus = EventBus()

        # Publisher (async):
        await bus.emit("orb:state", {"state": "thinking"})

        # Subscriber (async generator):
        async for data in bus.subscribe("orb:state"):
            print(data)

        # Publisher (from sync thread):
        bus.emit_sync("orb:state", {"state": "idle"})
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def emit(self, event: str, data: dict[str, Any] | None = None) -> None:
        """
        Publish an event to all subscribers.

        Parameters
        ----------
        event : str
            The event channel name.
        data : dict, optional
            Payload to send (defaults to empty dict).
        """
        payload = data or {}
        async with self._lock:
            queues = self._subscribers.get(event, [])
            # Remove any queues that have been garbage collected
            active = [q for q in queues if q is not None]
            self._subscribers[event] = active

        for queue in active:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                _log.warning(
                    "EventBus: dropped event on full queue (event=%s)", event
                )

    def emit_sync(self, event: str, data: dict[str, Any] | None = None) -> None:
        """
        Emit an event from a synchronous context (e.g. a background thread).

        Schedules the emit on the running event loop if one exists.
        Safe to call from threads.
        """
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(self.emit(event, data))
            )
        except RuntimeError:
            # No running loop — log and skip (non-critical)
            _log.debug(
                "EventBus.emit_sync: no running loop, skipping event=%s",
                event,
            )

    async def subscribe(
        self, event: str, max_queue: int = 100
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Subscribe to an event channel.

        Yields payloads as they arrive.  The caller should iterate
        in an ``async for`` loop.  When the caller breaks out of the
        loop, the subscription is automatically cleaned up.

        Parameters
        ----------
        event : str
            The event channel to subscribe to.
        max_queue : int
            Maximum buffered events (oldest dropped on overflow).

        Yields
        ------
        dict
            Event payload.
        """
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=max_queue)

        async with self._lock:
            self._subscribers[event].append(queue)

        try:
            while True:
                data = await queue.get()
                yield data
        finally:
            # Clean up on unsubscribe
            async with self._lock:
                try:
                    self._subscribers[event].remove(queue)
                except ValueError:
                    pass

    def subscriber_count(self, event: str) -> int:
        """Return the number of active subscribers for an event."""
        return len(self._subscribers.get(event, []))

    def __repr__(self) -> str:
        channels = {k: len(v) for k, v in self._subscribers.items() if v}
        return f"<EventBus channels={channels}>"


# ---------------------------------------------------------------------------
# Singleton instance — import this from other modules
# ---------------------------------------------------------------------------

event_bus = EventBus()
