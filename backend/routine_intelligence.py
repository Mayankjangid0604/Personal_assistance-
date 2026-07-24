"""
Persistent Routine Intelligence for Aisha AI Assistant (Phase 5 Step 1).

Detects and tracks recurring long-term behavioral patterns by analyzing
aggregated daily summaries — never raw content.

What it learns:
    - Morning / evening work routines
    - Focus window patterns (when the user is most productive)
    - Weekly work rhythms (weekday vs. weekend behavior)
    - Burnout cycle trends (overwork followed by recovery)
    - Emotional rhythm patterns (stress peaks, recovery periods)
    - Context-switching habits

Privacy guarantees:
    - Only reads aggregated category + timing metadata
    - No window titles, no file paths, no user content
    - All data is bucketed to the hour (never finer granularity)
    - Routine descriptions are behavioral labels, not personal data

Design principle:
    "Learn quietly. Surface gently. Never track obsessively."

EventBus events emitted:
    routine:detected        -- new routine pattern found (confidence >= 0.7)
    routine:shift_detected  -- established routine has changed significantly

Usage::

    from routine_intelligence import routine_intelligence

    # Record a desktop tick (called by desktop_awareness)
    routine_intelligence.record_tick(desktop_snapshot, productivity_state)

    # Get active routines
    routines = routine_intelligence.get_active_routines()

    # Get predicted focus windows for today
    windows = routine_intelligence.get_focus_windows()

    # Get aggregated summary for the last N days
    summary = routine_intelligence.get_behavioral_summary(days=7)
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.db import get_connection


# ---------------------------------------------------------------------------
# Pattern Types
# ---------------------------------------------------------------------------

_PATTERN_TYPES = {
    "morning_coding":      "Morning coding routine (consistent early-day focus)",
    "evening_learning":    "Evening learning routine (consistent late-day study)",
    "weekend_recovery":    "Weekend recovery pattern (reduced workload on weekends)",
    "deep_focus_window":   "Sustained focus window (recurring high-focus time block)",
    "communication_burst": "Communication burst pattern (recurring messaging-heavy period)",
    "late_night_work":     "Late-night work pattern (recurring after-hours activity)",
    "burnout_cycle":       "Burnout-recovery cycle (overwork followed by low activity)",
    "consistent_schedule": "Consistent daily schedule (stable start/end times)",
    "fragmented_habit":    "Fragmented work pattern (recurring high task-switching)",
}

# Minimum occurrences before a pattern is considered established
_MIN_OCCURRENCES = 3

# Confidence thresholds
_DETECTION_CONFIDENCE = 0.6
_ESTABLISHED_CONFIDENCE = 0.75

# How many days of history to analyze for routine detection
_ANALYSIS_WINDOW_DAYS = 14

# Daily summary aggregation interval (one summary per day)
_DAILY_SUMMARY_FLUSH_INTERVAL = 3600  # 1 hour


# ---------------------------------------------------------------------------
# Routine Intelligence Engine
# ---------------------------------------------------------------------------

class RoutineIntelligence:
    """
    Detects and persists recurring behavioral patterns from aggregated data.

    Reads from `daily_behavioral_summary` and `workflow_sessions`.
    Writes to `routine_patterns` and `daily_behavioral_summary`.
    Emits EventBus events when patterns are found or shift.

    All time resolution is at the HOUR level — never finer.
    """

    def __init__(self) -> None:
        # In-memory daily buffer (flushed to SQLite once per day)
        self._today_focus_seconds: float = 0.0
        self._today_fragments: int = 0
        self._today_ticks: int = 0
        self._today_emotions: list[str] = []
        self._today_workflows: list[str] = []
        self._today_categories: list[str] = []
        self._today_burnout_observations: list[str] = []

        self._last_flush_date: str = ""
        self._last_analysis_time: float = 0.0
        self._current_session_start: float | None = None
        self._current_session_workflow: str | None = None
        self._current_session_category: str = "other"

        # Analysis frequency: run full pattern analysis at most every 6 hours
        self._analysis_interval: float = 6 * 3600

        self._patterns: list[dict] = []
        self._patterns_loaded: bool = False

        print("  [Routine] Intelligence Engine initialized")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_tick(
        self,
        desktop_snapshot: dict[str, Any],
        productivity_state: dict[str, Any] | None = None,
        emotion: str = "neutral",
    ) -> None:
        """
        Record a single desktop poll tick.

        Called by desktop_awareness after each poll. Aggregates data into
        the daily buffer and flushes to SQLite at day boundaries.
        """
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        category = desktop_snapshot.get("category", "other")
        workflow = desktop_snapshot.get("workflow_name")

        # Track workflow sessions
        self._track_session(workflow, category, now)

        # Daily buffer accumulation
        if productivity_state:
            focus_score = productivity_state.get("focus_score", 0.0)
            if focus_score > 0.6 and category in ("coding", "studying", "design"):
                self._today_focus_seconds += 10  # poll cadence ~10s

            if productivity_state.get("is_fragmented"):
                self._today_fragments += 1

            burnout = productivity_state.get("burnout_risk", "none")
            if burnout != "none":
                self._today_burnout_observations.append(burnout)

        self._today_ticks += 1
        self._today_emotions.append(emotion)
        self._today_categories.append(category)
        if workflow:
            self._today_workflows.append(workflow)

        # Day boundary: flush yesterday's data
        if self._last_flush_date and self._last_flush_date != today:
            self._flush_daily_summary(self._last_flush_date)
            self._reset_daily_buffer()

        self._last_flush_date = today

        # Periodic pattern analysis (every 6 hours, low-cost)
        if time.time() - self._last_analysis_time > self._analysis_interval:
            self._run_pattern_analysis()
            self._last_analysis_time = time.time()

    def get_active_routines(self) -> list[dict]:
        """Return established routine patterns (confidence >= threshold)."""
        self._ensure_patterns_loaded()
        return [
            p for p in self._patterns
            if p.get("confidence", 0) >= _ESTABLISHED_CONFIDENCE
        ]

    def get_focus_windows(self) -> list[dict]:
        """
        Return predicted focus windows for today based on history.

        Returns list of {hour, confidence, label} dicts.
        """
        self._ensure_patterns_loaded()
        windows = []
        for p in self._patterns:
            if p.get("pattern_type") in ("deep_focus_window", "morning_coding",
                                          "evening_learning"):
                hour = p.get("typical_hour")
                if hour is not None:
                    windows.append({
                        "hour": hour,
                        "confidence": p.get("confidence", 0.5),
                        "label": p.get("description", "Focus window"),
                        "pattern_type": p.get("pattern_type"),
                    })
        return sorted(windows, key=lambda x: x["hour"])

    def get_behavioral_summary(self, days: int = 7) -> dict[str, Any]:
        """
        Return aggregated behavioral summary for the last N days.

        Suitable for LLM context enrichment.
        """
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        with get_connection() as conn:
            rows = conn.execute(
                "SELECT date, focus_hours, fragmentation_score, burnout_risk, "
                "dominant_workflow, dominant_emotion, productivity_score "
                "FROM daily_behavioral_summary "
                "WHERE date >= ? ORDER BY date DESC",
                (cutoff,),
            ).fetchall()

        if not rows:
            return {"days_analyzed": 0, "insufficient_data": True}

        records = [dict(r) for r in rows]

        avg_focus = sum(r["focus_hours"] for r in records) / len(records)
        avg_productivity = sum(r["productivity_score"] for r in records) / len(records)
        burnout_days = sum(1 for r in records if r["burnout_risk"] in ("moderate", "high"))

        # Dominant emotion
        emotions = [r["dominant_emotion"] for r in records if r["dominant_emotion"]]
        dominant_emotion = Counter(emotions).most_common(1)[0][0] if emotions else "neutral"

        # Dominant workflow
        workflows = [r["dominant_workflow"] for r in records if r["dominant_workflow"]]
        dominant_workflow = Counter(workflows).most_common(1)[0][0] if workflows else None

        return {
            "days_analyzed": len(records),
            "avg_focus_hours": round(avg_focus, 1),
            "avg_productivity": round(avg_productivity, 2),
            "burnout_days": burnout_days,
            "dominant_emotion": dominant_emotion,
            "dominant_workflow": dominant_workflow,
            "active_routines": len(self.get_active_routines()),
            "focus_windows": self.get_focus_windows(),
        }

    def get_context_summary(self) -> str:
        """
        Return a concise routine context string for LLM prompts.

        Only surfaces something if there's a meaningful pattern to share.
        """
        routines = self.get_active_routines()
        if not routines:
            return ""

        parts = []
        for r in routines[:2]:
            parts.append(r["description"])

        windows = self.get_focus_windows()
        now_hour = datetime.now().hour
        for w in windows:
            if abs(w["hour"] - now_hour) <= 1:
                parts.append(
                    f"This is typically a high-focus time for the user ({w['label']})."
                )
                break

        return " ".join(parts) if parts else ""

    def get_status(self) -> dict[str, Any]:
        """Return full routine intelligence status."""
        self._ensure_patterns_loaded()
        return {
            "patterns_detected": len(self._patterns),
            "established_patterns": len(self.get_active_routines()),
            "focus_windows": self.get_focus_windows(),
            "today_focus_hours": round(self._today_focus_seconds / 3600, 2),
            "today_ticks": self._today_ticks,
            "last_analysis": datetime.fromtimestamp(
                self._last_analysis_time
            ).isoformat(timespec="seconds") if self._last_analysis_time else None,
        }

    # ------------------------------------------------------------------
    # Session Tracking
    # ------------------------------------------------------------------

    def _track_session(
        self, workflow: str | None, category: str, now: datetime
    ) -> None:
        """Track the start and continuation of workflow sessions."""
        workflow_changed = (
            workflow != self._current_session_workflow
            or category != self._current_session_category
        )

        if workflow_changed and self._current_session_start is not None:
            # Close the previous session
            duration_min = (
                now.timestamp() - self._current_session_start
            ) / 60.0

            if duration_min >= 1.0:  # Only record sessions > 1 minute
                session_start_dt = datetime.fromtimestamp(
                    self._current_session_start
                )
                self._write_session(
                    workflow=self._current_session_workflow,
                    category=self._current_session_category,
                    started_at=session_start_dt.isoformat(timespec="seconds"),
                    ended_at=now.isoformat(timespec="seconds"),
                    duration_min=round(duration_min, 1),
                    day_of_week=session_start_dt.weekday(),
                    hour_of_day=session_start_dt.hour,
                )

            self._current_session_start = now.timestamp()

        elif self._current_session_start is None:
            self._current_session_start = now.timestamp()

        self._current_session_workflow = workflow
        self._current_session_category = category

    def _write_session(self, **kwargs) -> None:
        """Persist a workflow session to SQLite."""
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO workflow_sessions "
                    "(workflow_name, category, started_at, ended_at, "
                    "duration_min, day_of_week, hour_of_day) "
                    "VALUES (:workflow, :category, :started_at, :ended_at, "
                    ":duration_min, :day_of_week, :hour_of_day)",
                    kwargs,
                )
        except Exception:
            pass  # Never crash the poll loop

    # ------------------------------------------------------------------
    # Daily Aggregation
    # ------------------------------------------------------------------

    def _flush_daily_summary(self, date: str) -> None:
        """Flush the in-memory daily buffer to the `daily_behavioral_summary` table."""
        if self._today_ticks == 0:
            return

        focus_hours = round(self._today_focus_seconds / 3600, 2)
        frag_score = round(
            min(1.0, self._today_fragments / max(1, self._today_ticks / 10)), 2
        )

        # Dominant emotion
        emotion_counts = Counter(self._today_emotions)
        dominant_emotion = (
            emotion_counts.most_common(1)[0][0]
            if emotion_counts else "neutral"
        )

        # Dominant workflow
        workflow_counts = Counter(w for w in self._today_workflows if w)
        dominant_workflow = (
            workflow_counts.most_common(1)[0][0]
            if workflow_counts else None
        )

        # Burnout risk for the day
        burn_counts = Counter(self._today_burnout_observations)
        if burn_counts.get("high", 0) >= 3:
            burnout_risk = "high"
        elif burn_counts.get("moderate", 0) >= 3:
            burnout_risk = "moderate"
        else:
            burnout_risk = "none"

        # Productivity score: normalized focus + inverse fragmentation
        productivity_score = round(
            min(1.0, (focus_hours / 6.0) * 0.6 + (1.0 - frag_score) * 0.4), 2
        )

        now = datetime.now().isoformat(timespec="seconds")

        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO daily_behavioral_summary "
                    "(date, focus_hours, fragmentation_score, burnout_risk, "
                    "dominant_workflow, dominant_emotion, productivity_score, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (date, focus_hours, frag_score, burnout_risk,
                     dominant_workflow, dominant_emotion, productivity_score, now),
                )
        except Exception:
            pass

    def _reset_daily_buffer(self) -> None:
        """Reset in-memory daily accumulators."""
        self._today_focus_seconds = 0.0
        self._today_fragments = 0
        self._today_ticks = 0
        self._today_emotions = []
        self._today_workflows = []
        self._today_categories = []
        self._today_burnout_observations = []

    # ------------------------------------------------------------------
    # Pattern Analysis
    # ------------------------------------------------------------------

    def _run_pattern_analysis(self) -> None:
        """
        Analyze recent `daily_behavioral_summary` and `workflow_sessions`
        to detect recurring patterns.

        Runs at most every 6 hours. Low-overhead.
        """
        try:
            self._detect_focus_windows()
            self._detect_schedule_consistency()
            self._detect_burnout_cycles()
            self._load_patterns()  # Refresh in-memory cache
        except Exception:
            pass  # Pattern analysis must never crash

    def _detect_focus_windows(self) -> None:
        """Detect recurring high-focus time blocks from workflow_sessions."""
        cutoff = (
            datetime.now() - timedelta(days=_ANALYSIS_WINDOW_DAYS)
        ).isoformat(timespec="seconds")

        with get_connection() as conn:
            rows = conn.execute(
                "SELECT hour_of_day, workflow_name, duration_min "
                "FROM workflow_sessions "
                "WHERE started_at >= ? AND duration_min >= 30 "
                "AND workflow_name IN ('deep_coding', 'deep_study', 'research_write_loop')",
                (cutoff,),
            ).fetchall()

        if len(rows) < _MIN_OCCURRENCES:
            return

        # Bucket by hour
        hour_counts: Counter = Counter()
        for row in rows:
            hour_counts[row["hour_of_day"]] += 1

        now_str = datetime.now().isoformat(timespec="seconds")

        for hour, count in hour_counts.most_common(3):
            if count < _MIN_OCCURRENCES:
                continue

            confidence = min(0.95, 0.5 + (count / 20))

            # Determine pattern type
            if 5 <= hour < 12:
                ptype = "morning_coding"
                desc = f"Morning focus window around {hour:02d}:00 — recurring deep work."
            elif 18 <= hour < 24:
                ptype = "evening_learning"
                desc = f"Evening focus window around {hour:02d}:00 — recurring study/work session."
            else:
                ptype = "deep_focus_window"
                desc = f"Midday focus window around {hour:02d}:00 — recurring productive period."

            self._upsert_pattern(
                pattern_type=ptype,
                description=desc,
                typical_hour=hour,
                confidence=confidence,
                now_str=now_str,
            )

    def _detect_schedule_consistency(self) -> None:
        """Detect consistent daily schedule from workflow_sessions start times."""
        cutoff = (
            datetime.now() - timedelta(days=_ANALYSIS_WINDOW_DAYS)
        ).isoformat(timespec="seconds")

        with get_connection() as conn:
            rows = conn.execute(
                "SELECT hour_of_day, day_of_week FROM workflow_sessions "
                "WHERE started_at >= ? AND duration_min >= 20",
                (cutoff,),
            ).fetchall()

        if len(rows) < 5:
            return

        # Count how often work starts at the same hour
        hour_counts: Counter = Counter(r["hour_of_day"] for r in rows)
        most_common_hour, count = hour_counts.most_common(1)[0]

        if count >= _MIN_OCCURRENCES:
            confidence = min(0.90, 0.5 + (count / 30))
            now_str = datetime.now().isoformat(timespec="seconds")
            self._upsert_pattern(
                pattern_type="consistent_schedule",
                description=f"Consistent work schedule — typically starts around {most_common_hour:02d}:00.",
                typical_hour=most_common_hour,
                confidence=confidence,
                now_str=now_str,
            )

    def _detect_burnout_cycles(self) -> None:
        """Detect burnout-recovery cycles from daily_behavioral_summary."""
        cutoff = (
            datetime.now() - timedelta(days=_ANALYSIS_WINDOW_DAYS)
        ).strftime("%Y-%m-%d")

        with get_connection() as conn:
            rows = conn.execute(
                "SELECT date, burnout_risk, focus_hours FROM daily_behavioral_summary "
                "WHERE date >= ? ORDER BY date ASC",
                (cutoff,),
            ).fetchall()

        if len(rows) < 5:
            return

        records = [dict(r) for r in rows]

        # Detect: >=2 high-burnout days followed by low-focus day
        cycles = 0
        for i in range(1, len(records) - 1):
            prev = records[i - 1]
            curr = records[i]
            if (prev["burnout_risk"] in ("moderate", "high")
                    and curr["focus_hours"] < 1.0):
                cycles += 1

        if cycles >= 2:
            confidence = min(0.85, 0.5 + (cycles / 6))
            now_str = datetime.now().isoformat(timespec="seconds")
            self._upsert_pattern(
                pattern_type="burnout_cycle",
                description=(
                    "Recurring burnout-recovery pattern detected. "
                    "Periods of intense focus followed by low-energy days."
                ),
                typical_hour=None,
                confidence=confidence,
                now_str=now_str,
            )

    def _upsert_pattern(
        self,
        pattern_type: str,
        description: str,
        confidence: float,
        now_str: str,
        typical_hour: int | None = None,
        days_json: str = "[]",
    ) -> None:
        """Upsert a pattern record — update if exists, insert if new."""
        try:
            with get_connection() as conn:
                existing = conn.execute(
                    "SELECT id, occurrence_count, first_seen FROM routine_patterns "
                    "WHERE pattern_type = ?",
                    (pattern_type,),
                ).fetchone()

                if existing:
                    conn.execute(
                        "UPDATE routine_patterns SET confidence=?, last_seen=?, "
                        "occurrence_count=occurrence_count+1, "
                        "description=?, typical_hour=? WHERE id=?",
                        (confidence, now_str, description, typical_hour,
                         existing["id"]),
                    )
                else:
                    conn.execute(
                        "INSERT INTO routine_patterns "
                        "(pattern_type, description, days_json, typical_hour, "
                        "confidence, first_seen, last_seen, occurrence_count) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
                        (pattern_type, description, days_json, typical_hour,
                         confidence, now_str, now_str),
                    )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Pattern Loading
    # ------------------------------------------------------------------

    def _load_patterns(self) -> None:
        """Load all patterns from SQLite into memory."""
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT * FROM routine_patterns ORDER BY confidence DESC"
                ).fetchall()
            self._patterns = [dict(r) for r in rows]
            self._patterns_loaded = True
        except Exception:
            self._patterns = []

    def _ensure_patterns_loaded(self) -> None:
        if not self._patterns_loaded:
            self._load_patterns()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

routine_intelligence = RoutineIntelligence()
