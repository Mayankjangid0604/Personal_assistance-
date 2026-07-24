"""
Memory System for Aisha AI Assistant.

Provides two layers of memory backed by **SQLite**:

1. **Short-Term Memory**  -- Rolling buffer of the last N conversations
   (default 20).  Each entry stores user_input, role, and response.

2. **Long-Term Memory**  -- Persistent key-value store for important
   user information (name, goals, preferences, etc.).

Both layers are stored in ``database/aisha.db`` via the repository
pattern.  The in-memory deque is kept as a read-cache for fast access
by the brain pipeline, and every write operation is synchronously
persisted to SQLite.

Backward compatibility
----------------------
The public API (``Memory`` class, ``ConversationEntry``, module-level
``memory`` singleton) is **identical** to the JSON-backed version.
No consumer code needs to change.
"""

from __future__ import annotations

import copy
import json
import os
import sys
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

# Ensure database package is importable
_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from database.repositories import memory_repo


# ---------------------------------------------------------------------------
# Conversation Entry
# ---------------------------------------------------------------------------

class ConversationEntry:
    """A single conversation turn stored in short-term memory."""

    __slots__ = ("user_input", "role", "response", "timestamp")

    def __init__(
        self,
        user_input: str,
        role: str,
        response: str,
        timestamp: str | None = None,
    ) -> None:
        self.user_input = user_input
        self.role = role
        self.response = response
        self.timestamp = timestamp or datetime.now().isoformat(timespec="seconds")

    def to_dict(self) -> dict[str, str]:
        return {
            "user_input": self.user_input,
            "role": self.role,
            "response": self.response,
            "timestamp": self.timestamp,
        }

    def __repr__(self) -> str:
        return (
            f"ConversationEntry(role={self.role!r}, "
            f"input={self.user_input!r}, "
            f"response={self.response!r})"
        )


# ---------------------------------------------------------------------------
# Memory Manager
# ---------------------------------------------------------------------------

SHORT_TERM_LIMIT = 20  # max conversations kept in short-term memory


class Memory:
    """
    Central memory manager for Aisha.

    All write operations (``add_conversation``, ``save_user_info``,
    ``delete_user_info``, ``clear_*``) are automatically persisted to
    SQLite.  Data is loaded from the database when the ``Memory``
    instance is created.

    Attributes
    ----------
    short_term : deque[ConversationEntry]
        Fixed-size buffer holding the most recent conversations.
    long_term : dict[str, Any]
        Read-cache of user profile data (always synced with SQLite).
    """

    def __init__(self, short_term_limit: int = SHORT_TERM_LIMIT) -> None:
        self._short_term_limit = short_term_limit
        self.short_term: deque[ConversationEntry] = deque(
            maxlen=short_term_limit
        )
        self.long_term: dict[str, Any] = {}

        # Load saved data from SQLite
        self._load_from_db()

    # -- Persistence (private) --------------------------------------------

    def _load_from_db(self) -> None:
        """
        Load memory state from SQLite.

        Populates the in-memory deque and long_term dict from the
        database.  If the database is empty (first run), the system
        starts with empty memory.
        """
        try:
            # Restore conversations
            rows = memory_repo.get_recent_conversations(self._short_term_limit)
            for row in rows:
                self.short_term.append(ConversationEntry(
                    user_input=row.get("user_input", ""),
                    role=row.get("role", "assistant"),
                    response=row.get("response", ""),
                    timestamp=row.get("timestamp"),
                ))

            # Restore long-term memory
            self.long_term = memory_repo.get_all_user_info()

            print(f"  [Memory] Loaded from SQLite "
                  f"({len(self.short_term)} conversations, "
                  f"{len(self.long_term)} user info keys)")

        except Exception as e:
            print(f"  [Memory] DB load failed ({e}), starting fresh.")
            self.short_term.clear()
            self.long_term.clear()

    # -- Short-Term Memory ------------------------------------------------

    def add_conversation(
        self, user_input: str, role: str, response: str
    ) -> ConversationEntry:
        """
        Record a conversation turn.

        When the buffer is full the oldest entry is automatically dropped
        (``deque`` with ``maxlen`` handles this).

        Returns the newly created ``ConversationEntry``.
        """
        entry = ConversationEntry(user_input, role, response)
        self.short_term.append(entry)

        # Persist to SQLite
        memory_repo.save_conversation(
            user_input, role, response, entry.timestamp
        )
        # Trim DB to match the in-memory limit
        memory_repo.trim_conversations(self._short_term_limit)

        return entry

    def get_recent_conversations(self) -> list[ConversationEntry]:
        """Return a copy of the recent conversations (oldest first)."""
        return list(self.short_term)

    def get_last_conversation(self) -> ConversationEntry | None:
        """Return the most recent conversation, or ``None``."""
        return self.short_term[-1] if self.short_term else None

    def clear_short_term(self) -> None:
        """Wipe short-term memory."""
        self.short_term.clear()
        memory_repo.clear_conversations()

    # -- Long-Term Memory -------------------------------------------------

    def save_user_info(self, key: str, value: Any) -> None:
        """Store a piece of user information (overwrites if key exists)."""
        self.long_term[key.lower().strip()] = value
        memory_repo.save_user_info(key, value)

    def get_user_info(self, key: str) -> Any | None:
        """Retrieve stored user info by key, or ``None`` if absent."""
        return self.long_term.get(key.lower().strip())

    def get_all_user_info(self) -> dict[str, Any]:
        """Return a shallow copy of all stored user info."""
        return copy.copy(self.long_term)

    def delete_user_info(self, key: str) -> bool:
        """Remove a key from long-term memory. Returns ``True`` if it existed."""
        key = key.lower().strip()
        if key in self.long_term:
            del self.long_term[key]
            memory_repo.delete_user_info(key)
            return True
        return False

    def clear_long_term(self) -> None:
        """Wipe long-term memory."""
        self.long_term.clear()
        memory_repo.clear_user_info()

    # -- Utilities --------------------------------------------------------

    @property
    def short_term_count(self) -> int:
        return len(self.short_term)

    @property
    def short_term_capacity(self) -> int:
        return self._short_term_limit

    def __repr__(self) -> str:
        return (
            f"Memory(short_term={self.short_term_count}/"
            f"{self.short_term_capacity}, "
            f"long_term_keys={list(self.long_term.keys())})"
        )


# ---------------------------------------------------------------------------
# Module-level default instance (importable by other modules)
# ---------------------------------------------------------------------------

memory = Memory()


# ---------------------------------------------------------------------------
# Built-in Tests / Demo
# ---------------------------------------------------------------------------

def _run_tests() -> None:
    """Demonstrate both memory layers with SQLite persistence."""

    # Use a fresh Memory instance (it reads from SQLite)
    test_memory = Memory(short_term_limit=5)

    conversations = [
        ("Hey bro, what's up?",               "friend",     "Yo! What's good?"),
        ("Ma'am, please teach me Python",      "mentor",     "Let's break this down together."),
        ("Help me with this task",             "assistant",  "Sure, I will help you with that."),
        ("I miss you baby",                    "girlfriend", "Aww, I'm here for you!"),
        ("What is recursion?",                 "assistant",  "Let me explain that for you."),
        ("Dude, that movie was crazy!",        "friend",     "No way, for real?!"),
        ("Love you darling",                   "girlfriend", "You mean so much to me!"),
    ]

    print("=" * 65)
    print("  AISHA -- Memory System (SQLite)  --  Test Suite")
    print("=" * 65)

    print("\n  [1] Adding 7 conversations (limit = 5)...\n")
    for i, (inp, role, resp) in enumerate(conversations, 1):
        test_memory.add_conversation(inp, role, resp)
        print(f"      #{i}  added  |  role={role:<11}  |  \"{inp[:40]}\"")

    print(f"\n  [2] Short-term memory ({test_memory.short_term_count}/"
          f"{test_memory.short_term_capacity}):\n")

    for entry in test_memory.get_recent_conversations():
        print(f"      [{entry.role:>10}]  User: {entry.user_input}")
        print(f"                    Aisha: {entry.response}")
        print()

    print("  [3] Saving user info...")
    test_memory.save_user_info("name", "Rahul")
    test_memory.save_user_info("goal", "learn AI")

    print(f"      Stored: {test_memory.get_all_user_info()}\n")

    print("  [4] Retrieving user info...")
    print(f"      Name     : {test_memory.get_user_info('name')}")
    print(f"      Goal     : {test_memory.get_user_info('goal')}")

    print(f"\n  [5] Overflow check:")
    print(f"      Added 7 conversations, but only {test_memory.short_term_count} "
          f"remain (limit={test_memory.short_term_capacity}).")

    print("\n  [6] Reload test (new Memory instance from SQLite):")
    reloaded = Memory(short_term_limit=5)
    print(f"      Conversations loaded : {reloaded.short_term_count}")
    print(f"      Name remembered      : {reloaded.get_user_info('name')}")

    print()
    print("  " + "-" * 61)
    print("  All memory tests completed successfully.")
    print("=" * 65)


if __name__ == "__main__":
    _run_tests()
