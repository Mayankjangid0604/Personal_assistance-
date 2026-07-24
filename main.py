"""
Aisha AI Assistant -- Interactive Chat System.

Launches a terminal-based chat loop that connects the user to
Aisha's brain pipeline (role detection, emotion awareness,
adaptive personality, memory, task execution, and personalisation).

Supports two interaction modes:
    1. **Text Mode**  -- type in the terminal (default)
    2. **Voice Mode** -- speak into the microphone, Aisha speaks back

Autonomous behavior runs in the background and delivers proactive
messages (idle nudges, emotion follow-ups, goal reminders) when the
user is idle.

Usage:
    python main.py
"""

import os
import sys
import threading
import time

# ---------------------------------------------------------------------------
# Path setup -- allow imports from backend/
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.join(_PROJECT_ROOT, "backend")

if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from brain import handle_input, process_input, aisha_memory
from voice import listen, speak, is_microphone_available
from autonomous import get_autonomous_message, record_activity
from scheduler import start_reminder_checker, stop_reminder_checker


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXIT_COMMANDS = {"exit", "quit", "bye", "goodbye"}

WELCOME_MESSAGE = """
===========================================================
     _    ___ ____  _   _    _
    / \\  |_ _/ ___|| | | |  / \\
   / _ \\  | |\\___ \\| |_| | / _ \\
  / ___ \\ | | ___) |  _  |/ ___ \\
 /_/   \\_\\___|____/|_| |_/_/   \\_\\

  Your Personal AI Assistant
===========================================================
{mode_line}
  Type 'exit' to quit.
  Try saying: \"My name is ...\" to personalise the chat.

-----------------------------------------------------------
"""

GOODBYE_MESSAGE = """
-----------------------------------------------------------
  Goodbye{name_part}! Aisha will miss you. See you soon!
-----------------------------------------------------------
"""


# ---------------------------------------------------------------------------
# Autonomous Background Thread
# ---------------------------------------------------------------------------

_autonomous_stop = threading.Event()


def _autonomous_loop(speak_fn=None):
    """
    Background thread that periodically checks for autonomous messages.

    Runs every 10 seconds.  If a message fires, it prints (and optionally
    speaks) the message.  The thread exits when ``_autonomous_stop`` is set.
    """
    while not _autonomous_stop.is_set():
        try:
            msg = get_autonomous_message(aisha_memory)
            if msg:
                # Print on a new line so it doesn't collide with the input prompt
                print(f"\n  Aisha : {msg}")
                print()
                if speak_fn:
                    speak_fn(msg)
        except Exception:
            pass  # never crash the background thread

        # Check every 10 seconds
        _autonomous_stop.wait(10)


def _start_autonomous(speak_fn=None):
    """Start the autonomous behavior thread (daemon -- dies with main)."""
    t = threading.Thread(
        target=_autonomous_loop,
        args=(speak_fn,),
        daemon=True,
    )
    t.start()
    return t


# ---------------------------------------------------------------------------
# Mode Selection
# ---------------------------------------------------------------------------

def _select_mode() -> str:
    """
    Ask the user to choose between Text and Voice mode.

    Returns ``"text"`` or ``"voice"``.
    """
    print()
    print("  ==================================")
    print("    Choose your interaction mode:")
    print("  ==================================")
    print("    (1)  Text Mode   [keyboard]")
    print("    (2)  Voice Mode  [microphone]")
    print("  ==================================")
    print()

    while True:
        try:
            choice = input("  Enter 1 or 2: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Defaulting to Text Mode.\n")
            return "text"

        if choice == "1":
            return "text"
        elif choice == "2":
            return "voice"
        else:
            print("  Please enter 1 or 2.")


# ---------------------------------------------------------------------------
# Text Chat Loop
# ---------------------------------------------------------------------------

def _run_text_mode() -> None:
    """Run the standard keyboard-based chat loop."""

    mode_line = "  Mode: TEXT -- type your messages below."
    print(WELCOME_MESSAGE.format(mode_line=mode_line))

    # Start autonomous behavior in background (no speech in text mode)
    _start_autonomous(speak_fn=None)

    # Start reminder checker (prints alerts when reminders fire)
    start_reminder_checker(on_trigger=None)

    while True:
        try:
            user_input = input("  You   : ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            _print_goodbye()
            break

        if not user_input:
            continue

        if user_input.lower() in EXIT_COMMANDS:
            _print_goodbye()
            break

        # Record activity for autonomous system
        record_activity()

        try:
            result = process_input(user_input)
            print(f"  Aisha : {result.response}")
            print()
        except Exception as e:
            print(f"  Aisha : Oops, something went wrong. Let me try again.")
            print(f"          (Error: {e})")
            print()


# ---------------------------------------------------------------------------
# Voice Chat Loop
# ---------------------------------------------------------------------------

def _run_voice_mode() -> None:
    """Run the voice-based chat loop with speech-to-text and TTS."""

    # Verify microphone availability
    if not is_microphone_available():
        print()
        print("  [!] No microphone detected.")
        print("  [!] Make sure PyAudio is installed: pip install pyaudio")
        print("  [!] Falling back to Text Mode...\n")
        _run_text_mode()
        return

    mode_line = "  Mode: VOICE -- speak into your microphone."
    print(WELCOME_MESSAGE.format(mode_line=mode_line))

    # Greet the user with voice
    greeting = "Hello! I am Aisha, your personal AI assistant. You can start speaking now."
    print(f"  Aisha : {greeting}")
    speak(greeting)
    print()

    # Start autonomous behavior in background (with speech)
    _start_autonomous(speak_fn=speak)

    # Start reminder checker (prints + speaks alerts)
    start_reminder_checker(on_trigger=speak)

    while True:
        try:
            # Listen for speech
            print("  [Listening... speak now]")
            user_input = listen(timeout=8, phrase_time_limit=15)

            # No speech detected -- retry
            if user_input is None:
                print("  [No speech detected. Try again.]\n")
                continue

            print(f"  You   : {user_input}")

            # Check for exit commands
            if user_input.lower().strip() in EXIT_COMMANDS:
                goodbye_text = _get_goodbye_text()
                print(f"  Aisha : {goodbye_text}")
                speak(goodbye_text)
                break

            # Record activity for autonomous system
            record_activity()

            # Process through the brain pipeline
            result = process_input(user_input)
            print(f"  Aisha : {result.response}")

            # Speak the response aloud
            speak(result.response)
            print()

        except (EOFError, KeyboardInterrupt):
            print()
            goodbye_text = _get_goodbye_text()
            print(f"  Aisha : {goodbye_text}")
            speak(goodbye_text)
            break
        except Exception as e:
            error_msg = "Oops, something went wrong. Let me try again."
            print(f"  Aisha : {error_msg}")
            print(f"          (Error: {e})")
            speak(error_msg)
            print()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_goodbye_text() -> str:
    """Build a personalised goodbye string."""
    name = aisha_memory.get_user_info("name")
    if name:
        return f"Goodbye, {name}! I'll miss you. See you soon!"
    return "Goodbye! I'll miss you. See you soon!"


def _print_goodbye() -> None:
    """Print a personalised goodbye message (text mode)."""
    name = aisha_memory.get_user_info("name")
    name_part = f", {name}" if name else ""
    print(GOODBYE_MESSAGE.format(name_part=name_part))


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    """Main entry point -- select mode and launch the appropriate loop."""
    mode = _select_mode()

    if mode == "voice":
        _run_voice_mode()
    else:
        _run_text_mode()

    # Signal background threads to stop
    _autonomous_stop.set()
    stop_reminder_checker()


if __name__ == "__main__":
    main()
