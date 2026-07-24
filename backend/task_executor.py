"""
Task Execution System for Aisha AI Assistant.

Detects actionable commands from user input and executes system-level
tasks like opening applications, performing web searches, and basic
system operations.

Supported platforms: Windows (primary), with graceful fallback.
"""

import os
import re
import subprocess
import platform
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Task Result
# ---------------------------------------------------------------------------

class TaskResult(NamedTuple):
    """Holds the outcome of a task execution attempt."""
    detected: bool          # Was a task detected?
    task_name: str          # Human-readable task label
    success: bool           # Did execution succeed?
    message: str            # Status message for the user


# ---------------------------------------------------------------------------
# Application Registry
# ---------------------------------------------------------------------------

# Maps keyword triggers to (display_name, command).
# Commands are Windows-focused; extend per platform as needed.
APP_REGISTRY: dict[str, tuple[str, str]] = {
    # Keyword            (Display Name,        Command)
    "notepad":           ("Notepad",            "notepad"),
    "calculator":        ("Calculator",         "calc"),
    "calc":              ("Calculator",         "calc"),
    "chrome":            ("Google Chrome",      "start chrome"),
    "google chrome":     ("Google Chrome",      "start chrome"),
    "browser":           ("Default Browser",    "start chrome"),
    "paint":             ("Paint",              "mspaint"),
    "cmd":               ("Command Prompt",     "start cmd"),
    "command prompt":    ("Command Prompt",     "start cmd"),
    "terminal":          ("Command Prompt",     "start cmd"),
    "explorer":          ("File Explorer",      "explorer"),
    "file explorer":     ("File Explorer",      "explorer"),
    "files":             ("File Explorer",      "explorer"),
    "task manager":      ("Task Manager",       "taskmgr"),
    "settings":          ("Settings",           "start ms-settings:"),
    "word":              ("Microsoft Word",     "start winword"),
    "excel":             ("Microsoft Excel",    "start excel"),
    "powerpoint":        ("PowerPoint",         "start powerpnt"),
    "vscode":            ("VS Code",            "code"),
    "vs code":           ("VS Code",            "code"),
    "spotify":           ("Spotify",            "start spotify:"),
}


# ---------------------------------------------------------------------------
# System Task Registry
# ---------------------------------------------------------------------------

# Simple system-level actions triggered by keyword patterns.
SYSTEM_TASKS: dict[str, tuple[str, str]] = {
    # Keyword pattern     (Display Name,          Command)
    "shutdown":           ("Shutdown",             "shutdown /s /t 60"),
    "restart":            ("Restart",              "shutdown /r /t 60"),
    "lock":               ("Lock Screen",          "rundll32.exe user32.dll,LockWorkStation"),
    "screenshot":         ("Screenshot",           "snippingtool"),
    "snip":               ("Snipping Tool",        "snippingtool"),
}


# ---------------------------------------------------------------------------
# Task Detection Patterns
# ---------------------------------------------------------------------------

_OPEN_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bopen\s+(.+)",       re.IGNORECASE),
    re.compile(r"\blaunch\s+(.+)",     re.IGNORECASE),
    re.compile(r"\bstart\s+(.+)",      re.IGNORECASE),
    re.compile(r"\brun\s+(.+)",        re.IGNORECASE),
]

_CLOSE_PATTERN = re.compile(r"\bclose\s+(.+)", re.IGNORECASE)

_SYSTEM_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(shutdown)\b",      re.IGNORECASE),
    re.compile(r"\b(restart)\b",       re.IGNORECASE),
    re.compile(r"\b(lock)\s*(screen|pc|computer)?", re.IGNORECASE),
    re.compile(r"\b(screenshot)\b",    re.IGNORECASE),
    re.compile(r"\b(snip)\b",          re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# Detection Helpers
# ---------------------------------------------------------------------------

def _detect_open_task(user_input: str) -> tuple[str, str] | None:
    """
    Check if the user wants to open an application.

    Returns ``(display_name, command)`` or ``None``.
    """
    normalised = user_input.lower().strip()

    for pat in _OPEN_PATTERNS:
        m = pat.search(normalised)
        if m:
            app_name = m.group(1).strip().rstrip(".!?")

            # Direct lookup in app registry
            if app_name in APP_REGISTRY:
                return APP_REGISTRY[app_name]

            # Partial match: check if any registry key is in the input
            for key, (display, cmd) in APP_REGISTRY.items():
                if key in app_name:
                    return (display, cmd)

    return None


def _detect_close_task(user_input: str) -> tuple[str, str] | None:
    """
    Check if the user wants to close an application.

    Returns ``(display_name, taskkill_command)`` or ``None``.
    """
    m = _CLOSE_PATTERN.search(user_input.lower().strip())
    if not m:
        return None

    app_name = m.group(1).strip().rstrip(".!?")

    # Map common names to process names for taskkill
    process_map = {
        "notepad":    "notepad.exe",
        "chrome":     "chrome.exe",
        "calculator": "Calculator.exe",
        "calc":       "Calculator.exe",
        "paint":      "mspaint.exe",
        "explorer":   "explorer.exe",
        "word":       "WINWORD.EXE",
        "excel":      "EXCEL.EXE",
    }

    for key, proc in process_map.items():
        if key in app_name:
            return (key.title(), f"taskkill /im {proc} /f")

    return None


def _detect_system_task(user_input: str) -> tuple[str, str] | None:
    """
    Check if the user wants a system-level action.

    Returns ``(display_name, command)`` or ``None``.
    """
    normalised = user_input.lower().strip()

    for pat in _SYSTEM_PATTERNS:
        m = pat.search(normalised)
        if m:
            key = m.group(1).lower()
            if key in SYSTEM_TASKS:
                return SYSTEM_TASKS[key]

    return None


# ---------------------------------------------------------------------------
# Core Execution
# ---------------------------------------------------------------------------

def _run_command(command: str) -> bool:
    """
    Execute a system command silently.

    Returns ``True`` on success, ``False`` on failure.
    """
    try:
        subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


def is_task_command(user_input: str) -> bool:
    """Quick check: does this input look like a task command?"""
    normalised = user_input.lower().strip()
    task_verbs = ["open", "launch", "start", "run", "close", "shutdown",
                  "restart", "lock", "screenshot", "snip"]
    return any(normalised.startswith(v) or f" {v} " in f" {normalised} "
               for v in task_verbs)


def execute_task(user_input: str, dry_run: bool = False) -> TaskResult:
    """
    Detect and execute a task from *user_input*.

    Parameters
    ----------
    user_input : str
        Raw text from the user.
    dry_run : bool
        If ``True``, detect the task but don't actually execute it.
        Useful for testing.

    Returns
    -------
    TaskResult
        A named-tuple with ``detected``, ``task_name``, ``success``,
        and ``message`` fields.
    """
    if not user_input or not user_input.strip():
        return TaskResult(
            detected=False,
            task_name="none",
            success=False,
            message="No task detected.",
        )

    # --- Try: Open application ---
    open_result = _detect_open_task(user_input)
    if open_result:
        display, cmd = open_result
        if dry_run:
            return TaskResult(
                detected=True,
                task_name=f"open_{display.lower().replace(' ', '_')}",
                success=True,
                message=f"Opening {display}... (dry run)",
            )
        success = _run_command(cmd)
        return TaskResult(
            detected=True,
            task_name=f"open_{display.lower().replace(' ', '_')}",
            success=success,
            message=f"Opening {display}..." if success
                    else f"Failed to open {display}.",
        )

    # --- Try: Close application ---
    close_result = _detect_close_task(user_input)
    if close_result:
        display, cmd = close_result
        if dry_run:
            return TaskResult(
                detected=True,
                task_name=f"close_{display.lower()}",
                success=True,
                message=f"Closing {display}... (dry run)",
            )
        success = _run_command(cmd)
        return TaskResult(
            detected=True,
            task_name=f"close_{display.lower()}",
            success=success,
            message=f"Closing {display}..." if success
                    else f"Failed to close {display}.",
        )

    # --- Try: System task ---
    system_result = _detect_system_task(user_input)
    if system_result:
        display, cmd = system_result
        if dry_run:
            return TaskResult(
                detected=True,
                task_name=f"system_{display.lower().replace(' ', '_')}",
                success=True,
                message=f"Executing {display}... (dry run)",
            )
        success = _run_command(cmd)
        return TaskResult(
            detected=True,
            task_name=f"system_{display.lower().replace(' ', '_')}",
            success=success,
            message=f"Executing {display}..." if success
                    else f"Failed to execute {display}.",
        )

    # --- No task detected ---
    return TaskResult(
        detected=False,
        task_name="none",
        success=False,
        message="No task detected.",
    )


# ---------------------------------------------------------------------------
# Built-in Tests / Demo (dry_run mode -- nothing actually launches)
# ---------------------------------------------------------------------------

def _run_tests() -> None:
    """Test task detection in dry-run mode (no apps are actually opened)."""

    test_inputs = [
        # Open commands
        "Open Notepad",
        "open chrome",
        "Launch calculator",
        "open file explorer",
        "open vs code",
        "start paint",
        "open spotify",

        # Close commands
        "close notepad",
        "close chrome",

        # System commands
        "take a screenshot",
        "lock screen",

        # NOT a task
        "Tell me a joke",
        "Hey bro what's up",
        "My name is Rahul",
        "",
    ]

    print("=" * 65)
    print("  AISHA -- Task Executor  --  Test Suite (dry run)")
    print("=" * 65)

    for user_input in test_inputs:
        result = execute_task(user_input, dry_run=True)

        label = f'"{user_input}"' if user_input else '""'
        detected_str = "[TASK]" if result.detected else "[SKIP]"

        print(f"\n  {detected_str}  Input   : {label}")
        print(f"          Task    : {result.task_name}")
        print(f"          Message : {result.message}")

    print()
    print("  " + "-" * 61)
    print(f"  System   : {platform.system()} {platform.release()}")
    print(f"  Platform : {platform.platform()}")
    print("  Task executor test completed successfully.")
    print("=" * 65)


if __name__ == "__main__":
    _run_tests()
