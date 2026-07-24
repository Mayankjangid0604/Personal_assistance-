"""
SQLite Database Manager for Aisha AI Assistant.

Provides a thread-safe, WAL-mode SQLite connection factory and schema
initialisation.  All repository modules import ``get_connection()`` from
here to obtain a dedicated per-call connection.

Design decisions
----------------
* **WAL mode** -- allows concurrent readers + one writer without blocking.
* **check_same_thread=False** -- Flask, SSE, and the reminder-checker
  thread all need access; we serialise writes via SQLite's own locking.
* **Autocommit via context manager** -- every ``with get_connection()``
  block commits on success and rolls back on exception.
* **Schema is idempotent** -- ``CREATE TABLE IF NOT EXISTS`` lets us run
  ``init_db()`` on every startup without risk.

Usage::

    from database.db import get_connection, DB_PATH

    with get_connection() as conn:
        conn.execute("INSERT INTO ...")
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

# ---------------------------------------------------------------------------
# Database file path
# ---------------------------------------------------------------------------

_THIS_DIR = Path(__file__).resolve().parent
DB_PATH = _THIS_DIR / "aisha.db"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
-- Conversations (short-term memory)
CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_input  TEXT    NOT NULL,
    role        TEXT    NOT NULL DEFAULT 'assistant',
    response    TEXT    NOT NULL,
    timestamp   TEXT    NOT NULL
);

-- User profile (long-term memory)  -- key/value store
CREATE TABLE IF NOT EXISTS user_profile (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- Reminders
CREATE TABLE IF NOT EXISTS reminders (
    id          TEXT PRIMARY KEY,
    task        TEXT    NOT NULL,
    time        TEXT    NOT NULL,
    created_at  TEXT    NOT NULL,
    completed   INTEGER NOT NULL DEFAULT 0
);

-- Notifications
CREATE TABLE IF NOT EXISTS notifications (
    id          TEXT PRIMARY KEY,
    message     TEXT    NOT NULL,
    category    TEXT    NOT NULL DEFAULT 'general',
    source      TEXT    NOT NULL DEFAULT 'system',
    time        TEXT    NOT NULL,
    read        INTEGER NOT NULL DEFAULT 0
);

-- Journal entries
CREATE TABLE IF NOT EXISTS journal_entries (
    id              TEXT PRIMARY KEY,
    date            TEXT NOT NULL,
    time            TEXT NOT NULL,
    summary         TEXT NOT NULL,
    emotion         TEXT NOT NULL DEFAULT 'neutral',
    emotion_cause   TEXT,
    notes           TEXT
);

-- Habits
CREATE TABLE IF NOT EXISTS habits (
    name                TEXT PRIMARY KEY,
    streak              INTEGER NOT NULL DEFAULT 0,
    best_streak         INTEGER NOT NULL DEFAULT 0,
    total_completions   INTEGER NOT NULL DEFAULT 0,
    last_done           TEXT,
    created             TEXT NOT NULL
);

-- Learning interests
CREATE TABLE IF NOT EXISTS learning_interests (
    topic       TEXT PRIMARY KEY,
    count       INTEGER NOT NULL DEFAULT 0
);

-- Learning practice log
CREATE TABLE IF NOT EXISTS learning_practice_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    topic       TEXT NOT NULL,
    count       INTEGER NOT NULL DEFAULT 0,
    time        TEXT NOT NULL
);

-- Learning milestones / plans
CREATE TABLE IF NOT EXISTS learning_plans (
    id          TEXT PRIMARY KEY,
    topic       TEXT NOT NULL UNIQUE,
    created     TEXT NOT NULL,
    steps_json  TEXT NOT NULL
);

-- Automations (power tools)
CREATE TABLE IF NOT EXISTS automations (
    name        TEXT PRIMARY KEY,
    actions_json TEXT NOT NULL,
    created     TEXT NOT NULL
);

-- Routines
CREATE TABLE IF NOT EXISTS routines (
    name            TEXT PRIMARY KEY,
    steps_json      TEXT NOT NULL,
    time_of_day     TEXT
);

-- Shortcuts
CREATE TABLE IF NOT EXISTS shortcuts (
    alias       TEXT PRIMARY KEY,
    command     TEXT NOT NULL
);

-- Behaviour patterns (power tools analytics)
CREATE TABLE IF NOT EXISTS behaviour_peak_hours (
    hour        TEXT PRIMARY KEY,
    count       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS behaviour_commands (
    command     TEXT PRIMARY KEY,
    count       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS behaviour_topics_by_time (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    input       TEXT NOT NULL,
    period      TEXT NOT NULL,
    time        TEXT NOT NULL
);

-- Phase 2: Personality Adaptation
CREATE TABLE IF NOT EXISTS personality_preferences (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    confidence  REAL NOT NULL DEFAULT 0.5,
    updated_at  TEXT NOT NULL
);

-- Phase 2: Conversation Context / Topic Tracking
CREATE TABLE IF NOT EXISTS conversation_context (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    topic       TEXT NOT NULL,
    summary     TEXT,
    emotion     TEXT NOT NULL DEFAULT 'neutral',
    turn_count  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- Phase 2: Active Goals
CREATE TABLE IF NOT EXISTS conversation_goals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    goal        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'active',
    progress    REAL NOT NULL DEFAULT 0.0,
    context     TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- Phase 2: Session Summaries
CREATE TABLE IF NOT EXISTS session_summaries (
    session_id  TEXT PRIMARY KEY,
    summary     TEXT NOT NULL,
    topics      TEXT,
    dominant_emotion TEXT NOT NULL DEFAULT 'neutral',
    turn_count  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_conversations_timestamp
    ON conversations(timestamp);
CREATE INDEX IF NOT EXISTS idx_reminders_completed
    ON reminders(completed, time);
CREATE INDEX IF NOT EXISTS idx_notifications_read
    ON notifications(read, time);
CREATE INDEX IF NOT EXISTS idx_journal_date
    ON journal_entries(date);
CREATE INDEX IF NOT EXISTS idx_context_session
    ON conversation_context(session_id);
CREATE INDEX IF NOT EXISTS idx_goals_status
    ON conversation_goals(status);
CREATE INDEX IF NOT EXISTS idx_session_summaries_created
    ON session_summaries(created_at);

-- =====================================================================
-- Phase 3: Cognitive AI Companion System
-- =====================================================================

-- Semantic memory vectors (tiered: working / short_term / long_term)
CREATE TABLE IF NOT EXISTS semantic_memory (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tier          TEXT NOT NULL DEFAULT 'working',
    source        TEXT NOT NULL,
    source_id     TEXT,
    text          TEXT NOT NULL,
    embedding     TEXT,
    emotion       TEXT DEFAULT 'neutral',
    importance    REAL DEFAULT 0.5,
    access_count  INTEGER DEFAULT 0,
    created_at    TEXT NOT NULL,
    last_accessed TEXT
);

-- TF-IDF vocabulary persistence
CREATE TABLE IF NOT EXISTS semantic_vocab (
    term          TEXT PRIMARY KEY,
    doc_freq      INTEGER NOT NULL DEFAULT 1,
    idf           REAL
);

-- Life episodes (milestone, event, routine, struggle)
CREATE TABLE IF NOT EXISTS episodes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    category      TEXT NOT NULL,
    summary       TEXT NOT NULL,
    emotion       TEXT DEFAULT 'neutral',
    people        TEXT,
    importance    REAL DEFAULT 0.5,
    occurred_at   TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

-- Detected life patterns
CREATE TABLE IF NOT EXISTS life_patterns (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern       TEXT NOT NULL,
    category      TEXT NOT NULL,
    frequency     INTEGER DEFAULT 1,
    last_seen     TEXT NOT NULL,
    context       TEXT
);

-- Cognitive plans (adaptive roadmaps)
CREATE TABLE IF NOT EXISTS cognitive_plans (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    goal          TEXT NOT NULL,
    steps_json    TEXT NOT NULL,
    status        TEXT DEFAULT 'active',
    progress      REAL DEFAULT 0.0,
    adaptations   INTEGER DEFAULT 0,
    context       TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

-- Phase 3 indexes
CREATE INDEX IF NOT EXISTS idx_semantic_tier
    ON semantic_memory(tier);
CREATE INDEX IF NOT EXISTS idx_semantic_source
    ON semantic_memory(source, source_id);
CREATE INDEX IF NOT EXISTS idx_semantic_importance
    ON semantic_memory(importance DESC);
CREATE INDEX IF NOT EXISTS idx_episodes_category
    ON episodes(category);
CREATE INDEX IF NOT EXISTS idx_episodes_occurred
    ON episodes(occurred_at);
CREATE INDEX IF NOT EXISTS idx_life_patterns_category
    ON life_patterns(category);
CREATE INDEX IF NOT EXISTS idx_cognitive_plans_status
    ON cognitive_plans(status);

-- =====================================================================
-- Phase 5: Persistent Adaptive AI Ecosystem
-- =====================================================================

-- Workflow session history (Step 1)
CREATE TABLE IF NOT EXISTS workflow_sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_name TEXT,
    category      TEXT NOT NULL DEFAULT 'other',
    started_at    TEXT NOT NULL,
    ended_at      TEXT,
    duration_min  REAL DEFAULT 0.0,
    day_of_week   INTEGER NOT NULL DEFAULT 0,
    hour_of_day   INTEGER NOT NULL DEFAULT 0
);

-- Daily behavioral aggregates (Step 1)
CREATE TABLE IF NOT EXISTS daily_behavioral_summary (
    date                TEXT PRIMARY KEY,
    focus_hours         REAL NOT NULL DEFAULT 0.0,
    fragmentation_score REAL NOT NULL DEFAULT 0.5,
    burnout_risk        TEXT NOT NULL DEFAULT 'none',
    dominant_workflow   TEXT,
    dominant_emotion    TEXT NOT NULL DEFAULT 'neutral',
    productivity_score  REAL NOT NULL DEFAULT 0.5,
    updated_at          TEXT NOT NULL
);

-- Detected routine patterns (Step 1)
CREATE TABLE IF NOT EXISTS routine_patterns (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_type     TEXT NOT NULL,
    description      TEXT NOT NULL,
    days_json        TEXT NOT NULL DEFAULT '[]',
    typical_hour     INTEGER,
    confidence       REAL NOT NULL DEFAULT 0.5,
    first_seen       TEXT NOT NULL,
    last_seen        TEXT NOT NULL,
    occurrence_count INTEGER NOT NULL DEFAULT 1
);

-- Long-term behavioral model dimensions (Step 2)
CREATE TABLE IF NOT EXISTS behavioral_model (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    dimension      TEXT NOT NULL UNIQUE,
    trend_direction TEXT NOT NULL DEFAULT 'stable',
    trend_strength REAL NOT NULL DEFAULT 0.0,
    week_value     REAL NOT NULL DEFAULT 0.5,
    month_value    REAL NOT NULL DEFAULT 0.5,
    updated_at     TEXT NOT NULL
);

-- Reflective insights cache (Step 3)
CREATE TABLE IF NOT EXISTS cognitive_reflections (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    insight_type   TEXT NOT NULL,
    content        TEXT NOT NULL,
    context_json   TEXT,
    generated_at   TEXT NOT NULL,
    relevance_score REAL NOT NULL DEFAULT 0.5,
    shown_count    INTEGER NOT NULL DEFAULT 0,
    last_shown_at  TEXT
);

-- Natural language automation recipes (Step 4)
CREATE TABLE IF NOT EXISTS automation_recipes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger_description TEXT NOT NULL,
    action_description  TEXT NOT NULL,
    trigger_type        TEXT NOT NULL,
    action_type         TEXT NOT NULL,
    params_json         TEXT NOT NULL DEFAULT '{}',
    enabled             INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT NOT NULL,
    last_triggered      TEXT
);

-- Ecosystem timeline events (Step 5)
CREATE TABLE IF NOT EXISTS ecosystem_timeline (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type   TEXT NOT NULL,
    summary      TEXT NOT NULL,
    context_json TEXT,
    occurred_at  TEXT NOT NULL
);

-- Personality dimension snapshots (Step 6)
CREATE TABLE IF NOT EXISTS personality_snapshots (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date    TEXT NOT NULL UNIQUE,
    dimensions_json  TEXT NOT NULL,
    behavioral_context TEXT
);

-- Life management goals with burnout awareness (Step 7)
CREATE TABLE IF NOT EXISTS life_goals (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    title             TEXT NOT NULL,
    description       TEXT,
    target_date       TEXT,
    status            TEXT NOT NULL DEFAULT 'active',
    progress          REAL NOT NULL DEFAULT 0.0,
    burnout_adjusted  INTEGER NOT NULL DEFAULT 0,
    checkpoint_json   TEXT NOT NULL DEFAULT '[]',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

-- Device session continuity records (Step 8)
CREATE TABLE IF NOT EXISTS device_sessions (
    id                  TEXT PRIMARY KEY,
    device_id           TEXT NOT NULL,
    device_name         TEXT NOT NULL DEFAULT 'primary',
    session_start       TEXT NOT NULL,
    session_end         TEXT,
    cognitive_state_json TEXT
);

-- Phase 5 indexes
CREATE INDEX IF NOT EXISTS idx_workflow_sessions_started
    ON workflow_sessions(started_at);
CREATE INDEX IF NOT EXISTS idx_workflow_sessions_workflow
    ON workflow_sessions(workflow_name);
CREATE INDEX IF NOT EXISTS idx_routine_patterns_type
    ON routine_patterns(pattern_type);
CREATE INDEX IF NOT EXISTS idx_behavioral_model_dimension
    ON behavioral_model(dimension);
CREATE INDEX IF NOT EXISTS idx_reflections_type
    ON cognitive_reflections(insight_type);
CREATE INDEX IF NOT EXISTS idx_reflections_shown
    ON cognitive_reflections(shown_count, last_shown_at);
CREATE INDEX IF NOT EXISTS idx_automation_recipes_enabled
    ON automation_recipes(enabled);
CREATE INDEX IF NOT EXISTS idx_ecosystem_timeline_occurred
    ON ecosystem_timeline(occurred_at);
CREATE INDEX IF NOT EXISTS idx_life_goals_status
    ON life_goals(status);

-- =====================================================================
-- Phase 6: Deeply Personalized Cognitive AI Partner
-- =====================================================================

-- Deep personalization dimensions (Step 1)
CREATE TABLE IF NOT EXISTS deep_personalization (
    dimension       TEXT PRIMARY KEY,
    value           REAL NOT NULL DEFAULT 0.5,
    confidence      REAL NOT NULL DEFAULT 0.1,
    observations    INTEGER NOT NULL DEFAULT 0,
    drift_this_month REAL NOT NULL DEFAULT 0.0,
    updated_at      TEXT NOT NULL
);

-- Emotional timing observation log (Step 2)
CREATE TABLE IF NOT EXISTS emotional_timing_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type      TEXT NOT NULL,
    was_appropriate  INTEGER NOT NULL DEFAULT 1,
    context_json    TEXT,
    observed_at     TEXT NOT NULL
);

-- Multi-step automation recipes (Step 3)
CREATE TABLE IF NOT EXISTS multi_step_recipes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    description     TEXT NOT NULL,
    trigger_type    TEXT NOT NULL,
    trigger_value   TEXT,
    enabled         INTEGER NOT NULL DEFAULT 1,
    status          TEXT NOT NULL DEFAULT 'active',
    created_at      TEXT NOT NULL,
    last_triggered  TEXT
);

-- Individual actions in a multi-step recipe (Step 3)
CREATE TABLE IF NOT EXISTS multi_step_recipe_actions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id       INTEGER NOT NULL,
    step_order      INTEGER NOT NULL,
    action_type     TEXT NOT NULL,
    params_json     TEXT NOT NULL DEFAULT '{}',
    label           TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    FOREIGN KEY (recipe_id) REFERENCES multi_step_recipes(id)
);

-- LLM-generated reflective insights (Step 4)
CREATE TABLE IF NOT EXISTS llm_reflections (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    reflection_text TEXT NOT NULL,
    context_summary TEXT,
    quality_score   REAL NOT NULL DEFAULT 0.5,
    engagement_score REAL NOT NULL DEFAULT 0.0,
    shown_count     INTEGER NOT NULL DEFAULT 0,
    generated_at    TEXT NOT NULL,
    last_shown_at   TEXT
);

-- Proactive orchestration events (Step 7)
CREATE TABLE IF NOT EXISTS proactive_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type      TEXT NOT NULL,
    suggestion      TEXT NOT NULL,
    context_json    TEXT,
    was_accepted    INTEGER,
    created_at      TEXT NOT NULL
);

-- Phase 6 indexes
CREATE INDEX IF NOT EXISTS idx_deep_personalization_dim
    ON deep_personalization(dimension);
CREATE INDEX IF NOT EXISTS idx_emotional_timing_type
    ON emotional_timing_log(event_type, observed_at);
CREATE INDEX IF NOT EXISTS idx_multi_step_recipes_enabled
    ON multi_step_recipes(enabled);
CREATE INDEX IF NOT EXISTS idx_multi_step_actions_recipe
    ON multi_step_recipe_actions(recipe_id, step_order);
CREATE INDEX IF NOT EXISTS idx_llm_reflections_shown
    ON llm_reflections(shown_count, generated_at);
CREATE INDEX IF NOT EXISTS idx_proactive_events_created
    ON proactive_events(created_at);

-- =====================================================================
-- Phase 7: Collaborative Cognitive Intelligence Environment
-- =====================================================================

-- Projects (long-term, conceptual tracking)
CREATE TABLE IF NOT EXISTS projects (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT NOT NULL,
    description   TEXT,
    domain        TEXT NOT NULL DEFAULT 'general',
    status        TEXT NOT NULL DEFAULT 'active',
    trajectory    TEXT NOT NULL DEFAULT 'on_track',
    progress      REAL NOT NULL DEFAULT 0.0,
    blockers_json TEXT NOT NULL DEFAULT '[]',
    context_json  TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

-- Project milestones
CREATE TABLE IF NOT EXISTS project_milestones (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    INTEGER NOT NULL,
    title         TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    progress      REAL NOT NULL DEFAULT 0.0,
    notes         TEXT,
    order_idx     INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    completed_at  TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

-- Cognitive workspaces (persistent idea spaces)
CREATE TABLE IF NOT EXISTS cognitive_workspaces (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT NOT NULL,
    description   TEXT,
    workspace_type TEXT NOT NULL DEFAULT 'general',
    status        TEXT NOT NULL DEFAULT 'active',
    summary       TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

-- Workspace nodes (individual ideas/notes/concepts)
CREATE TABLE IF NOT EXISTS workspace_nodes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id  INTEGER NOT NULL,
    content       TEXT NOT NULL,
    node_type     TEXT NOT NULL DEFAULT 'note',
    importance    REAL NOT NULL DEFAULT 0.5,
    tags_json     TEXT NOT NULL DEFAULT '[]',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    FOREIGN KEY (workspace_id) REFERENCES cognitive_workspaces(id)
);

-- Links between workspace nodes
CREATE TABLE IF NOT EXISTS node_links (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id     INTEGER NOT NULL,
    target_id     INTEGER NOT NULL,
    relationship  TEXT NOT NULL DEFAULT 'related',
    weight        REAL NOT NULL DEFAULT 0.5,
    created_at    TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES workspace_nodes(id),
    FOREIGN KEY (target_id) REFERENCES workspace_nodes(id)
);

-- Research sessions
CREATE TABLE IF NOT EXISTS research_sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    topic         TEXT NOT NULL,
    domain        TEXT NOT NULL DEFAULT 'general',
    status        TEXT NOT NULL DEFAULT 'active',
    findings_json TEXT NOT NULL DEFAULT '[]',
    questions_json TEXT NOT NULL DEFAULT '[]',
    sources_json  TEXT NOT NULL DEFAULT '[]',
    depth_score   REAL NOT NULL DEFAULT 0.0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

-- Knowledge graph nodes (adaptive concept nodes)
CREATE TABLE IF NOT EXISTS knowledge_graph_nodes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    concept       TEXT NOT NULL UNIQUE,
    domain        TEXT NOT NULL DEFAULT 'general',
    importance    REAL NOT NULL DEFAULT 0.5,
    access_count  INTEGER NOT NULL DEFAULT 0,
    context_json  TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL,
    last_accessed TEXT NOT NULL
);

-- Knowledge graph edges (weighted relationships)
CREATE TABLE IF NOT EXISTS knowledge_graph_edges (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       INTEGER NOT NULL,
    target_id       INTEGER NOT NULL,
    relationship    TEXT NOT NULL DEFAULT 'related_to',
    weight          REAL NOT NULL DEFAULT 0.5,
    evidence_count  INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    last_reinforced TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES knowledge_graph_nodes(id),
    FOREIGN KEY (target_id) REFERENCES knowledge_graph_nodes(id)
);

-- Phase 7 indexes
CREATE INDEX IF NOT EXISTS idx_projects_status
    ON projects(status);
CREATE INDEX IF NOT EXISTS idx_projects_domain
    ON projects(domain);
CREATE INDEX IF NOT EXISTS idx_project_milestones_project
    ON project_milestones(project_id, order_idx);
CREATE INDEX IF NOT EXISTS idx_cognitive_workspaces_status
    ON cognitive_workspaces(status);
CREATE INDEX IF NOT EXISTS idx_workspace_nodes_workspace
    ON workspace_nodes(workspace_id);
CREATE INDEX IF NOT EXISTS idx_node_links_source
    ON node_links(source_id);
CREATE INDEX IF NOT EXISTS idx_node_links_target
    ON node_links(target_id);
CREATE INDEX IF NOT EXISTS idx_research_sessions_status
    ON research_sessions(status);
CREATE INDEX IF NOT EXISTS idx_kg_nodes_concept
    ON knowledge_graph_nodes(concept);
CREATE INDEX IF NOT EXISTS idx_kg_edges_source
    ON knowledge_graph_edges(source_id);

-- =====================================================================
-- Phase 8: Bounded Autonomous Cognitive Ecosystem
-- =====================================================================

-- Human Oversight Framework settings (Step 1)
CREATE TABLE IF NOT EXISTS human_oversight_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- Persistent execution audit log (Step 1)
CREATE TABLE IF NOT EXISTS autonomy_audit_log (
    action_id   TEXT PRIMARY KEY,
    action      TEXT NOT NULL,
    params_json TEXT NOT NULL,
    attribution TEXT NOT NULL,
    reasoning   TEXT NOT NULL,
    confidence  REAL NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    detail      TEXT,
    risk_level  TEXT NOT NULL,
    timestamp   TEXT NOT NULL
);

-- Persistent rollback registry (Step 1)
CREATE TABLE IF NOT EXISTS rollback_registry (
    action_id       TEXT PRIMARY KEY,
    undo_action     TEXT NOT NULL,
    undo_params_json TEXT NOT NULL,
    description     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active',
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_autonomy_audit_status
    ON autonomy_audit_log(status, timestamp);
"""


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

def _create_connection() -> sqlite3.Connection:
    """Create a new SQLite connection with optimal settings."""
    conn = sqlite3.connect(
        str(DB_PATH),
        check_same_thread=False,
        timeout=10,
    )
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_connection():
    """
    Yield a SQLite connection as a context manager.

    Commits on success, rolls back on exception, always closes.

    Usage::

        with get_connection() as conn:
            conn.execute("INSERT INTO ...")
    """
    conn = _create_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """
    Create all tables and indexes if they don't exist.

    Safe to call on every startup (idempotent).
    """
    with get_connection() as conn:
        conn.executescript(_SCHEMA)
    print(f"  [DB] Initialised SQLite database at {DB_PATH}")


# Run on import -- ensures schema exists before any repository uses it
init_db()
