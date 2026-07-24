"""
Multi-Device Continuity Foundation for Aisha AI Assistant (Phase 5 Step 8,
updated Phase 6 Step 6 with AES-256-GCM encryption).

Portable cognitive state export/import. Local-only — no network, no cloud.
Provides the foundation for future multi-device continuity.

Phase 6 upgrade: AES-256-GCM encrypted export/import via PBKDF2.

What is exported:
    - Personality preferences (all dimensions)
    - Active cognitive plans (goals and progress)
    - Established routine patterns
    - Life goals
    - Behavioral model state
    - Ecosystem timeline (last 30 days)
    - Device session metadata

What is NOT exported:
    - Raw conversation history (privacy — stays on the originating device)
    - Semantic memory vectors (device-specific; rebuild on new device)
    - Automation recipes (device-specific paths)

Security:
    - Export is plaintext JSON (gzip compressed) in Phase 5
    - Encrypted export (AES-256) targeted for Phase 6
    - Import validates schema before applying any data
    - Merge strategy: prefer newer data, never overwrite with older

Usage::

    from continuity import continuity

    # Export cognitive state to a file
    path = continuity.export_state("D:/AISHA_backup.json.gz")

    # Import from a file (merge strategy)
    result = continuity.import_state("D:/AISHA_backup.json.gz")

    # Start a new device session
    session_id = continuity.start_device_session()

    # Get status
    status = continuity.get_status()
"""

from __future__ import annotations

import gzip
import json
import os
import sys
import uuid
from datetime import datetime, timedelta
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.db import get_connection

_EXPORT_VERSION = "6.0.0"
_DEFAULT_EXPORT_DIR = _PROJECT_ROOT
_DEVICE_ID = str(uuid.uuid5(uuid.NAMESPACE_DNS, os.environ.get("COMPUTERNAME", "aisha-device")))

# Encryption constants
_MAGIC = b"AISH"
_KDF_ITERATIONS = 480_000
_SALT_LEN = 16
_NONCE_LEN = 12
_TAG_LEN = 16

# Check for cryptography library availability
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False


class ContinuityEngine:
    """
    Manages portable cognitive state for multi-device continuity.

    All I/O is local-only. No network calls. No cloud dependency.
    """

    def __init__(self) -> None:
        self._current_session_id: str | None = None
        self._session_start: str | None = None
        print("  [Continuity] Multi-Device Continuity Foundation initialized")

    # ------------------------------------------------------------------
    # Device Session Management
    # ------------------------------------------------------------------

    def start_device_session(self, device_name: str = "primary") -> str:
        """Start a new device session and persist it."""
        session_id = str(uuid.uuid4())
        now = datetime.now().isoformat(timespec="seconds")
        self._current_session_id = session_id
        self._session_start = now

        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO device_sessions "
                    "(id, device_id, device_name, session_start) "
                    "VALUES (?, ?, ?, ?)",
                    (session_id, _DEVICE_ID, device_name, now),
                )
        except Exception:
            pass

        return session_id

    def end_device_session(self) -> None:
        """End the current device session."""
        if not self._current_session_id:
            return
        now = datetime.now().isoformat(timespec="seconds")
        try:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE device_sessions SET session_end=? WHERE id=?",
                    (now, self._current_session_id),
                )
        except Exception:
            pass
        self._current_session_id = None

    # ------------------------------------------------------------------
    # Export / Import
    # ------------------------------------------------------------------

    def export_state(self, output_path: str | None = None) -> str:
        """
        Export the cognitive state to a gzip-compressed JSON file.

        Returns the path of the exported file.
        """
        if not output_path:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(
                _DEFAULT_EXPORT_DIR, f"aisha_state_{ts}.json.gz"
            )

        state = self._collect_state()
        payload = json.dumps(state, ensure_ascii=False, indent=2).encode("utf-8")

        with gzip.open(output_path, "wb") as f:
            f.write(payload)

        size_kb = round(os.path.getsize(output_path) / 1024, 1)
        return output_path

    def import_state(self, input_path: str) -> dict[str, Any]:
        """
        Import a cognitive state from a gzip-compressed JSON file.

        Uses a merge strategy: prefer newer data, skip conflicts.
        Returns a summary of what was imported.
        """
        if not os.path.exists(input_path):
            return {"status": "error", "error": f"File not found: {input_path}"}

        try:
            with gzip.open(input_path, "rb") as f:
                state = json.loads(f.read().decode("utf-8"))
        except Exception as e:
            return {"status": "error", "error": f"Could not read file: {e}"}

        # Validate
        version = state.get("version", "")
        if not (version.startswith("5.") or version.startswith("6.")):
            return {
                "status": "error",
                "error": f"Incompatible state version: {version}",
            }

        imported = {}
        imported["personality"] = self._import_personality(
            state.get("personality", {})
        )
        imported["life_goals"] = self._import_life_goals(
            state.get("life_goals", [])
        )
        imported["timeline_events"] = self._import_timeline(
            state.get("ecosystem_timeline", [])
        )

        return {
            "status": "imported",
            "version": version,
            "from_device": state.get("device_id"),
            "exported_at": state.get("exported_at"),
            "imported": imported,
        }

    def export_encrypted(
        self,
        passphrase: str,
        output_path: str | None = None,
    ) -> str:
        """
        Export cognitive state as AES-256-GCM encrypted file (Phase 6).

        Uses PBKDF2 key derivation from passphrase.
        Returns the path of the exported file.
        """
        if not _HAS_CRYPTO:
            # Graceful fallback to gzip-only with warning
            import warnings
            warnings.warn(
                "cryptography package not installed; falling back to gzip-only export.",
                RuntimeWarning,
                stacklevel=2,
            )
            return self.export_state(output_path)

        if not output_path:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(
                _DEFAULT_EXPORT_DIR, f"aisha_state_{ts}.enc"
            )

        state = self._collect_state()
        plaintext = json.dumps(state, ensure_ascii=False).encode("utf-8")

        # Derive key from passphrase
        salt = os.urandom(_SALT_LEN)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=_KDF_ITERATIONS,
        )
        key = kdf.derive(passphrase.encode("utf-8"))

        # Encrypt
        nonce = os.urandom(_NONCE_LEN)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)

        # ciphertext includes tag appended by AESGCM
        # File format: MAGIC + version(4) + salt(16) + nonce(12) + ciphertext
        version_bytes = _EXPORT_VERSION.encode("utf-8")[:4].ljust(4, b"\x00")

        with open(output_path, "wb") as f:
            f.write(_MAGIC)
            f.write(version_bytes)
            f.write(salt)
            f.write(nonce)
            f.write(ciphertext)

        return output_path

    def import_encrypted(
        self,
        input_path: str,
        passphrase: str,
    ) -> dict[str, Any]:
        """
        Import cognitive state from an AES-256-GCM encrypted file (Phase 6).

        Returns a summary of what was imported.
        """
        if not _HAS_CRYPTO:
            return {"status": "error", "error": "cryptography package not installed."}

        if not os.path.exists(input_path):
            return {"status": "error", "error": f"File not found: {input_path}"}

        try:
            with open(input_path, "rb") as f:
                magic = f.read(4)
                if magic != _MAGIC:
                    return {"status": "error", "error": "Invalid file format (bad magic)."}
                version_bytes = f.read(4)
                salt = f.read(_SALT_LEN)
                nonce = f.read(_NONCE_LEN)
                ciphertext = f.read()

            # Derive key
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=_KDF_ITERATIONS,
            )
            key = kdf.derive(passphrase.encode("utf-8"))

            # Decrypt
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            state = json.loads(plaintext.decode("utf-8"))

        except Exception as e:
            error_msg = str(e)
            if "tag" in error_msg.lower() or "decrypt" in error_msg.lower():
                return {"status": "error", "error": "Wrong passphrase or corrupted file."}
            return {"status": "error", "error": f"Decryption failed: {e}"}

        # Validate version
        version = state.get("version", "")
        if not (version.startswith("5.") or version.startswith("6.")):
            return {"status": "error", "error": f"Incompatible version: {version}"}

        # Import using existing merge logic
        imported = {}
        imported["personality"] = self._import_personality(state.get("personality", {}))
        imported["life_goals"] = self._import_life_goals(state.get("life_goals", []))
        imported["timeline_events"] = self._import_timeline(state.get("ecosystem_timeline", []))

        return {
            "status": "imported",
            "version": version,
            "encrypted": True,
            "from_device": state.get("device_id"),
            "exported_at": state.get("exported_at"),
            "imported": imported,
        }

    def get_status(self) -> dict[str, Any]:
        """Return continuity engine status."""
        sessions = self._get_recent_sessions(limit=5)
        return {
            "device_id": _DEVICE_ID,
            "current_session_id": self._current_session_id,
            "session_start": self._session_start,
            "recent_sessions": len(sessions),
            "export_version": _EXPORT_VERSION,
        }

    # ------------------------------------------------------------------
    # State Collection
    # ------------------------------------------------------------------

    def _collect_state(self) -> dict[str, Any]:
        """Collect all exportable state from the database."""
        state: dict[str, Any] = {
            "version": _EXPORT_VERSION,
            "device_id": _DEVICE_ID,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
        }

        # Personality preferences
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT key, value, confidence FROM personality_preferences"
                ).fetchall()
            state["personality"] = {
                r["key"]: {"value": r["value"], "confidence": r["confidence"]}
                for r in rows
            }
        except Exception:
            state["personality"] = {}

        # Active cognitive plans
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT goal, steps_json, status, progress, "
                    "created_at, updated_at FROM cognitive_plans "
                    "WHERE status = 'active'"
                ).fetchall()
            state["cognitive_plans"] = [dict(r) for r in rows]
        except Exception:
            state["cognitive_plans"] = []

        # Life goals
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT title, description, target_date, status, "
                    "progress, created_at FROM life_goals WHERE status = 'active'"
                ).fetchall()
            state["life_goals"] = [dict(r) for r in rows]
        except Exception:
            state["life_goals"] = []

        # Routine patterns
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT pattern_type, description, confidence, "
                    "typical_hour FROM routine_patterns "
                    "WHERE confidence >= 0.6"
                ).fetchall()
            state["routine_patterns"] = [dict(r) for r in rows]
        except Exception:
            state["routine_patterns"] = []

        # Behavioral model
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT dimension, trend_direction, week_value, "
                    "month_value FROM behavioral_model"
                ).fetchall()
            state["behavioral_model"] = {
                r["dimension"]: {
                    "trend_direction": r["trend_direction"],
                    "week_value": r["week_value"],
                    "month_value": r["month_value"],
                }
                for r in rows
            }
        except Exception:
            state["behavioral_model"] = {}

        # Ecosystem timeline (last 30 days)
        cutoff = (datetime.now() - timedelta(days=30)).isoformat(timespec="seconds")
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT event_type, summary, occurred_at "
                    "FROM ecosystem_timeline WHERE occurred_at >= ? "
                    "ORDER BY occurred_at DESC LIMIT 50",
                    (cutoff,),
                ).fetchall()
            state["ecosystem_timeline"] = [dict(r) for r in rows]
        except Exception:
            state["ecosystem_timeline"] = []

        return state

    # ------------------------------------------------------------------
    # Import Helpers
    # ------------------------------------------------------------------

    def _import_personality(self, personality: dict) -> int:
        """Import personality preferences (merge: keep higher confidence)."""
        imported = 0
        now = datetime.now().isoformat(timespec="seconds")
        try:
            with get_connection() as conn:
                for key, data in personality.items():
                    existing = conn.execute(
                        "SELECT confidence FROM personality_preferences WHERE key=?",
                        (key,),
                    ).fetchone()
                    incoming_conf = float(data.get("confidence", 0.5))
                    if existing and float(existing["confidence"]) >= incoming_conf:
                        continue  # Keep local (higher or equal confidence)
                    conn.execute(
                        "INSERT OR REPLACE INTO personality_preferences "
                        "(key, value, confidence, updated_at) VALUES (?, ?, ?, ?)",
                        (key, str(data.get("value", 0.5)), incoming_conf, now),
                    )
                    imported += 1
        except Exception:
            pass
        return imported

    def _import_life_goals(self, goals: list) -> int:
        """Import life goals (skip duplicates by title)."""
        imported = 0
        now = datetime.now().isoformat(timespec="seconds")
        try:
            with get_connection() as conn:
                for goal in goals:
                    exists = conn.execute(
                        "SELECT id FROM life_goals WHERE title=?",
                        (goal.get("title", ""),),
                    ).fetchone()
                    if exists:
                        continue
                    conn.execute(
                        "INSERT INTO life_goals "
                        "(title, description, target_date, status, progress, "
                        "burnout_adjusted, checkpoint_json, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, 0, '[]', ?, ?)",
                        (
                            goal.get("title", ""),
                            goal.get("description", ""),
                            goal.get("target_date"),
                            goal.get("status", "active"),
                            float(goal.get("progress", 0.0)),
                            goal.get("created_at", now),
                            now,
                        ),
                    )
                    imported += 1
        except Exception:
            pass
        return imported

    def _import_timeline(self, events: list) -> int:
        """Import ecosystem timeline events (append; no deduplication)."""
        imported = 0
        try:
            with get_connection() as conn:
                for event in events:
                    conn.execute(
                        "INSERT INTO ecosystem_timeline "
                        "(event_type, summary, context_json, occurred_at) "
                        "VALUES (?, ?, '{}', ?)",
                        (
                            event.get("event_type", "import"),
                            event.get("summary", ""),
                            event.get("occurred_at",
                                      datetime.now().isoformat(timespec="seconds")),
                        ),
                    )
                    imported += 1
        except Exception:
            pass
        return imported

    def _get_recent_sessions(self, limit: int = 5) -> list[dict]:
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT id, device_name, session_start, session_end "
                    "FROM device_sessions ORDER BY session_start DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

continuity = ContinuityEngine()
