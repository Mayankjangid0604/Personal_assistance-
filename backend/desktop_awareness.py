"""
Desktop Awareness System for Aisha AI Assistant (Phase 3 Step 5 / Phase 4 Step 1).

Understands the user's active desktop environment using Windows APIs:
    - Active window detection (title + process name)
    - App categorization (coding, browsing, studying, gaming, etc.)
    - Session detection (sustained activity in one category)
    - Clipboard awareness (type detection: code, URL, text)

Privacy-first:
    - Only reads window titles and process names
    - No content capture, no keylogging, no file watching
    - Clipboard: type detection only, not stored

Requirements:
    - pywin32 (installed)
    - psutil (installed)

EventBus events:
    desktop:activity     -- current activity snapshot
    desktop:session      -- sustained session detected
    workflow:detected    -- a meaningful workflow has been identified (via WorkflowIntelligence)
    workflow:changed     -- user switched to a different workflow
    workflow:overload    -- multitasking overload detected

Usage::

    from desktop_awareness import desktop_awareness

    # Get current activity
    activity = desktop_awareness.get_current_activity()

    # Check if in a coding session
    if desktop_awareness.is_coding():
        ...

    # Get session info
    session = desktop_awareness.get_session()
"""

from __future__ import annotations

import os
import re
import sys
import time
from datetime import datetime
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)


# ---------------------------------------------------------------------------
# App Categorization Rules
# ---------------------------------------------------------------------------

# Maps window title patterns to activity categories
_CATEGORY_RULES: list[tuple[str, str]] = [
    # Coding
    (r"visual studio code", "coding"),
    (r"vs code", "coding"),
    (r"pycharm", "coding"),
    (r"intellij", "coding"),
    (r"sublime text", "coding"),
    (r"atom", "coding"),
    (r"vim", "coding"),
    (r"neovim", "coding"),
    (r"android studio", "coding"),
    (r"terminal", "coding"),
    (r"powershell", "coding"),
    (r"cmd\.exe", "coding"),
    (r"windows terminal", "coding"),
    (r"git bash", "coding"),
    (r"jupyter", "coding"),
    (r"\.py\b", "coding"),
    (r"\.js\b", "coding"),
    (r"\.tsx?\b", "coding"),
    (r"\.java\b", "coding"),

    # Browsing
    (r"chrome", "browsing"),
    (r"firefox", "browsing"),
    (r"edge", "browsing"),
    (r"brave", "browsing"),
    (r"opera", "browsing"),
    (r"safari", "browsing"),

    # Study/docs
    (r"pdf", "studying"),
    (r"word", "studying"),
    (r"powerpoint", "studying"),
    (r"google docs", "studying"),
    (r"notion", "studying"),
    (r"obsidian", "studying"),
    (r"onenote", "studying"),
    (r"anki", "studying"),
    (r"coursera", "studying"),
    (r"udemy", "studying"),
    (r"khan academy", "studying"),

    # Communication
    (r"discord", "communication"),
    (r"slack", "communication"),
    (r"teams", "communication"),
    (r"whatsapp", "communication"),
    (r"telegram", "communication"),
    (r"outlook", "communication"),
    (r"gmail", "communication"),

    # Gaming
    (r"steam", "gaming"),
    (r"epic games", "gaming"),
    (r"minecraft", "gaming"),
    (r"valorant", "gaming"),

    # Media
    (r"spotify", "media"),
    (r"youtube", "media"),
    (r"netflix", "media"),
    (r"vlc", "media"),

    # Design
    (r"figma", "design"),
    (r"photoshop", "design"),
    (r"illustrator", "design"),
    (r"canva", "design"),
]

# Compile patterns for performance
_COMPILED_RULES = [(re.compile(p, re.IGNORECASE), cat) for p, cat in _CATEGORY_RULES]

# Session detection: minimum time in one category to count as a session
SESSION_THRESHOLD_SECONDS = 600  # 10 minutes


# ---------------------------------------------------------------------------
# Windows API Helpers
# ---------------------------------------------------------------------------

def _get_foreground_window_info() -> dict[str, str]:
    """
    Get the active window's title and process name.

    Uses pywin32 and psutil. Returns empty dict on failure.
    """
    try:
        import win32gui
        import win32process
        import psutil

        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return {"title": "", "process": "", "pid": 0}

        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)

        try:
            proc = psutil.Process(pid)
            process_name = proc.name()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            process_name = ""

        return {"title": title, "process": process_name, "pid": pid}

    except ImportError:
        return {"title": "", "process": "", "pid": 0}
    except Exception:
        return {"title": "", "process": "", "pid": 0}


def _get_clipboard_type() -> str:
    """
    Detect what type of content is on the clipboard.

    Returns: 'code', 'url', 'text', 'empty', 'unknown'
    Does NOT read or store clipboard content.
    """
    try:
        import win32clipboard

        win32clipboard.OpenClipboard()
        try:
            if not win32clipboard.IsClipboardFormatAvailable(1):  # CF_TEXT
                return "empty"

            data = win32clipboard.GetClipboardData(13)  # CF_UNICODETEXT
            if not data:
                return "empty"

            text = str(data).strip()[:500]  # Only check first 500 chars

            # URL detection
            if re.match(r"https?://", text):
                return "url"

            # Code detection (heuristics)
            code_signals = [
                "def ", "class ", "import ", "function ", "const ",
                "var ", "let ", "return ", "if (", "for (",
                "{", "}", "=>", "==", "!=",
            ]
            if sum(1 for s in code_signals if s in text) >= 2:
                return "code"

            return "text"

        finally:
            win32clipboard.CloseClipboard()

    except ImportError:
        return "unknown"
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Desktop Awareness Engine
# ---------------------------------------------------------------------------

class DesktopAwareness:
    """
    Tracks desktop activity and detects work sessions.

    Polls the active window and categorizes the user's activity.
    Detects sustained sessions (>10 minutes in one category).
    """

    def __init__(self) -> None:
        self._current_category: str = "unknown"
        self._session_category: str | None = None
        self._session_start: float = 0.0
        self._last_poll: float = 0.0
        self._category_time: dict[str, float] = {}  # category → seconds
        print("  [Desktop] Awareness initialized")

    def poll(self) -> dict[str, Any]:
        """
        Poll the current desktop state.

        Returns activity snapshot:
            window_title, process, category, clipboard_type,
            session_active, session_duration
        """
        now = time.time()
        window = _get_foreground_window_info()
        title = window.get("title", "")
        process = window.get("process", "")

        # Categorize
        category = self._categorize(title, process)

        # Track time in category
        if self._last_poll > 0:
            elapsed = now - self._last_poll
            self._category_time[category] = (
                self._category_time.get(category, 0) + elapsed
            )

        self._last_poll = now
        old_category = self._current_category
        self._current_category = category

        # Session detection
        if category == old_category and category != "unknown":
            if self._session_category != category:
                self._session_category = category
                self._session_start = now
        else:
            self._session_category = category
            self._session_start = now

        session_duration = now - self._session_start if self._session_category else 0
        session_active = session_duration >= SESSION_THRESHOLD_SECONDS

        clipboard = _get_clipboard_type()

        snapshot = {
            "window_title": title[:100],
            "process": process,
            "category": category,
            "clipboard_type": clipboard,
            "session_active": session_active,
            "session_category": self._session_category if session_active else None,
            "session_duration_min": round(session_duration / 60, 1),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }

        # Feed into workflow intelligence engine (Phase 4)
        try:
            from workflow_intelligence import workflow_intelligence
            wf_state = workflow_intelligence.update(snapshot)
            snapshot["workflow"] = wf_state.get("active_workflow")
            snapshot["workflow_label"] = wf_state.get("workflow_label")
            snapshot["workflow_overload"] = wf_state.get("overload", False)
        except Exception:
            snapshot["workflow"] = None
            snapshot["workflow_label"] = None
            snapshot["workflow_overload"] = False

        return snapshot

    def _categorize(self, title: str, process: str) -> str:
        """Categorize the current window activity."""
        combined = f"{title} {process}"

        for pattern, category in _COMPILED_RULES:
            if pattern.search(combined):
                return category

        return "other"

    def get_current_activity(self) -> dict[str, Any]:
        """Get the current activity without a full poll."""
        return self.poll()

    def is_coding(self) -> bool:
        """Check if the user is currently coding."""
        return self._current_category == "coding"

    def is_studying(self) -> bool:
        """Check if the user is currently studying."""
        return self._current_category == "studying"

    def is_deep_work(self) -> bool:
        """
        Check if the user is in a deep work session.

        Deep work = sustained coding or studying session (>10 min).
        """
        if self._session_category not in ("coding", "studying"):
            return False
        if not self._session_start:
            return False
        duration = time.time() - self._session_start
        return duration >= SESSION_THRESHOLD_SECONDS

    def get_session(self) -> dict[str, Any] | None:
        """Return current session info if active."""
        if not self._session_category or not self._session_start:
            return None

        duration = time.time() - self._session_start
        if duration < SESSION_THRESHOLD_SECONDS:
            return None

        return {
            "category": self._session_category,
            "duration_minutes": round(duration / 60, 1),
            "started_at": datetime.fromtimestamp(self._session_start).isoformat(
                timespec="seconds"
            ),
        }

    def get_activity_summary(self, reset: bool = False) -> dict[str, float]:
        """
        Return time spent in each category (in minutes).

        Optionally reset counters.
        """
        summary = {
            cat: round(secs / 60, 1)
            for cat, secs in self._category_time.items()
            if secs > 0
        }
        if reset:
            self._category_time.clear()
        return summary

    def get_workflow(self) -> dict[str, Any] | None:
        """Return the active workflow from the workflow intelligence engine."""
        try:
            from workflow_intelligence import workflow_intelligence
            return workflow_intelligence.get_active_workflow()
        except Exception:
            return None

    def get_status(self) -> dict[str, Any]:
        """Return full awareness status."""
        session = self.get_session()
        return {
            "current_category": self._current_category,
            "session": session,
            "deep_work": self.is_deep_work(),
            "activity_summary": self.get_activity_summary(),
            "workflow": self.get_workflow(),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

desktop_awareness = DesktopAwareness()
