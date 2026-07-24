"""
Voice System for Aisha AI Assistant.

Provides two core capabilities:

1. **listen()**  -- Captures speech from the microphone and converts it
   to text using Google's speech recognition API.

2. **speak(text)** -- Converts text to speech using the pyttsx3 offline
   TTS engine (Windows SAPI5 / espeak on Linux).

Dependencies:
    pip install SpeechRecognition pyttsx3 pyaudio
"""

import sys
import platform

# ---------------------------------------------------------------------------
# Text-to-Speech Engine (pyttsx3)
# ---------------------------------------------------------------------------

import pyttsx3

# Lazy-initialised engine (created on first use)
_tts_engine: pyttsx3.Engine | None = None


def _get_tts_engine() -> pyttsx3.Engine:
    """Return the shared pyttsx3 engine, creating it on first call."""
    global _tts_engine
    if _tts_engine is None:
        _tts_engine = pyttsx3.init()

        # -- Configure voice properties -----------------------------------
        _tts_engine.setProperty("rate", 175)      # words per minute
        _tts_engine.setProperty("volume", 1.0)     # 0.0 to 1.0

        # Try to pick a female voice if available
        voices = _tts_engine.getProperty("voices")
        for voice in voices:
            if "female" in voice.name.lower() or "zira" in voice.name.lower():
                _tts_engine.setProperty("voice", voice.id)
                break

    return _tts_engine


def speak(text: str) -> bool:
    """
    Convert *text* to speech and play it through the speakers.

    Parameters
    ----------
    text : str
        The text to speak aloud.

    Returns
    -------
    bool
        ``True`` if speech completed successfully, ``False`` on error.
    """
    if not text or not text.strip():
        return False

    try:
        engine = _get_tts_engine()
        engine.say(text)
        engine.runAndWait()
        return True
    except Exception as e:
        print(f"  [Voice] TTS error: {e}")
        return False


def set_voice_rate(rate: int) -> None:
    """Change speaking speed (default 175 WPM)."""
    engine = _get_tts_engine()
    engine.setProperty("rate", rate)


def set_voice_volume(volume: float) -> None:
    """Change volume (0.0 to 1.0)."""
    engine = _get_tts_engine()
    engine.setProperty("volume", max(0.0, min(1.0, volume)))


def list_voices() -> list[dict[str, str]]:
    """Return a list of available voice dicts (id, name, lang)."""
    engine = _get_tts_engine()
    voices = engine.getProperty("voices")
    return [
        {"id": v.id, "name": v.name, "languages": str(v.languages)}
        for v in voices
    ]


# ---------------------------------------------------------------------------
# Speech-to-Text (SpeechRecognition + Microphone)
# ---------------------------------------------------------------------------

import speech_recognition as sr

_recogniser = sr.Recognizer()

# Tweak recogniser sensitivity
_recogniser.energy_threshold = 4000       # ambient noise threshold
_recogniser.dynamic_energy_threshold = True
_recogniser.pause_threshold = 1.0          # seconds of silence before stop


def listen(
    timeout: int = 5,
    phrase_time_limit: int = 10,
    language: str = "en-IN",
) -> str | None:
    """
    Listen to the microphone and return recognised text.

    Parameters
    ----------
    timeout : int
        Max seconds to wait for speech to *start*.
    phrase_time_limit : int
        Max seconds of speech to capture.
    language : str
        Language code for recognition (default ``"en-IN"``).

    Returns
    -------
    str or None
        The recognised text, or ``None`` if nothing was understood.
    """
    try:
        with sr.Microphone() as source:
            print("  [Voice] Adjusting for ambient noise...")
            _recogniser.adjust_for_ambient_noise(source, duration=0.5)

            print("  [Voice] Listening...")
            audio = _recogniser.listen(
                source,
                timeout=timeout,
                phrase_time_limit=phrase_time_limit,
            )

        print("  [Voice] Recognising...")
        text = _recogniser.recognize_google(audio, language=language)
        return text.strip()

    except sr.WaitTimeoutError:
        print("  [Voice] No speech detected (timed out).")
        return None
    except sr.UnknownValueError:
        print("  [Voice] Could not understand the audio.")
        return None
    except sr.RequestError as e:
        print(f"  [Voice] Google API error: {e}")
        return None
    except OSError as e:
        print(f"  [Voice] Microphone error: {e}")
        print("  [Voice] Make sure PyAudio is installed: pip install pyaudio")
        return None
    except Exception as e:
        print(f"  [Voice] Unexpected error: {e}")
        return None


def is_microphone_available() -> bool:
    """Check if a microphone is accessible."""
    try:
        mic_list = sr.Microphone.list_microphone_names()
        return len(mic_list) > 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Built-in Tests / Demo
# ---------------------------------------------------------------------------

def _run_tests() -> None:
    """Demonstrate both voice capabilities."""

    print("=" * 65)
    print("  AISHA -- Voice System  --  Test Suite")
    print("=" * 65)

    # -- Phase 1: TTS test ------------------------------------------------
    print("\n  [Phase 1] Text-to-Speech (pyttsx3):\n")

    test_phrases = [
        "Hello! I am Aisha, your personal AI assistant.",
        "How can I help you today?",
    ]

    for phrase in test_phrases:
        print(f"  Speaking : \"{phrase}\"")
        success = speak(phrase)
        status = "[PASS]" if success else "[FAIL]"
        print(f"  Status   : {status}")
        print()

    # -- Phase 2: Voice listing -------------------------------------------
    print("  [Phase 2] Available voices:\n")

    voices = list_voices()
    for i, v in enumerate(voices[:5]):  # show max 5
        print(f"    {i+1}. {v['name']}")

    if len(voices) > 5:
        print(f"    ... and {len(voices) - 5} more")
    print()

    # -- Phase 3: Microphone check ----------------------------------------
    print("  [Phase 3] Microphone check:\n")

    mic_available = is_microphone_available()
    print(f"    Microphone available : {mic_available}")

    if mic_available:
        try:
            mic_names = sr.Microphone.list_microphone_names()
            print(f"    Default microphone   : {mic_names[0]}")
        except Exception:
            pass

    print()

    # -- Phase 4: Speech-to-Text test (only if mic is available) ----------
    print("  [Phase 4] Speech-to-Text (microphone):\n")

    if not mic_available:
        print("    [SKIP] No microphone detected. Skipping listen test.")
        print("    Install PyAudio if needed: pip install pyaudio")
    else:
        print("    Say something (you have 5 seconds)...")
        print()
        heard = listen(timeout=5, phrase_time_limit=8)

        if heard:
            print(f"\n    You said : \"{heard}\"")
            print(f"    Aisha responding...")
            speak(f"I heard you say: {heard}")
            print("    [PASS] Speech-to-text working!")
        else:
            print("\n    [INFO] No speech detected. This is normal if you")
            print("           didn't speak or PyAudio isn't installed.")

    # -- Summary ----------------------------------------------------------
    print()
    print("  " + "-" * 61)
    print(f"  Platform : {platform.system()} {platform.release()}")
    print(f"  TTS      : pyttsx3 (offline)")
    print(f"  STT      : Google Speech Recognition (online)")
    print(f"  Mic      : {'Available' if mic_available else 'Not found'}")
    print("  Voice system test completed.")
    print("=" * 65)


if __name__ == "__main__":
    _run_tests()
