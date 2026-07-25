# AISHA Architecture Guide

**Last updated:** Phase 11 — Production Integration Layer

This document describes AISHA's layering, with emphasis on the three
cross-cutting platforms added in Phases 9–11. It does not re-describe the
pre-existing cognitive subsystems (memory, personality, planning, oversight,
knowledge graph, etc.) — those are unchanged and documented in their own
module docstrings.

## Layering

```
┌─────────────────────────────────────────────────────────────┐
│  Electron + React (frontend/)                                │
├─────────────────────────────────────────────────────────────┤
│  Quart async API (backend/server.py)                         │
├─────────────────────────────────────────────────────────────┤
│  Service Layer (backend/services/)         ← Phase 11, NEW   │
│  Config · Provider · Plugin · Memory · Notification ·        │
│  Workspace · Agent · Desktop                                  │
├───────────────────────┬───────────────────┬───────────────────┤
│  Provider Platform     │  Plugin Platform  │  Existing         │
│  (backend/providers/)  │  (backend/plugins/)│  Cognitive Core   │
│  Phase 9, NEW          │  Phase 10, NEW    │  (brain.py, ...)  │
├───────────────────────┴───────────────────┴───────────────────┤
│  SQLite (database/) — repository pattern                      │
└─────────────────────────────────────────────────────────────┘
```

Three platforms share one design: a **registry/manager** for discovery and
lifecycle, a **capability index**, **health monitoring**, and a **uniform
result type** that never raises to the caller (`ProviderResponse`,
`PluginResult`, `ServiceResult`).

## The Service Layer (Phase 11)

`backend/services/` is the newest layer. It exists to give **new** backend
code (the REST API, future Electron-facing endpoints) one obvious, testable
seam, instead of importing subsystem internals directly.

| Service | Wraps | Notes |
|---|---|---|
| `ConfigurationService` | app-level settings | layered: defaults < JSON file < `AISHA_*` env < runtime overrides |
| `ProviderService` | `providers.get_registry()` | generate/stream/route/health/latency |
| `PluginService` | `plugins.PluginManager` | invoke/lifecycle/health/discovery |
| `MemoryService` | `database.memory.Memory` | short-term + long-term facade |
| `NotificationService` | `notifications` module functions | notify/list/read/clear |
| `WorkspaceService` | `cognitive_workspace` singleton | idea-graph workspace facade |
| `AgentService` | `distributed_agents` coordinator | bounded multi-agent gather + arbitration log |
| `DesktopService` | `desktop_awareness` singleton | **read-only** activity/session/workflow queries |

All eight are wired by `services.get_services()` → `ServiceContainer`, which
also exposes `health_report()` for a fleet-wide health snapshot (the seam for
a future Performance Dashboard).

### Design rules

1. **Constructor injection.** Every service takes its wrapped dependency as
   an optional constructor argument; omitted, it lazily imports and
   constructs the real default. This is what makes every service unit-testable
   with a fake, with zero mocking/patching.
2. **Never raise.** Public methods return `ServiceResult(ok, data, error, ...)`.
3. **`health()` is mandatory** on every service.

### Scope decision: additive, not a rewrite

The instruction that motivated this layer asked for these services to become
"the only public interfaces used by the backend," which would mean rewiring
every existing consumer across ~60 backend modules in one pass. That was
**deliberately not done** — it directly conflicts with the project's own
"never rewrite working modules" rule, and a big-bang rewire across a
34k-line codebase is exactly how regressions get introduced into a working
system. Instead:

- Existing modules (`brain.py`, skills, `server.py`, etc.) keep their direct
  imports of `memory`, `notifications`, `cognitive_workspace`, and so on.
  **Nothing that already worked was touched.**
- The service layer is additive: it can be adopted incrementally by new code
  (the REST API expansion, an Electron IPC bridge) without a flag day.

### `DesktopService` is intentionally read-only

Production Milestone "Computer Control" (launch/close apps, window
management, screenshots, hotkeys, ...) is explicitly required to pass through
Human Oversight, the Automation Governor, the Rollback Registry, and Audit
Logs before touching the OS. `DesktopService` only exposes what
`desktop_awareness` already observes (active window category, focus session,
workflow pattern) — it does not, and should not, gain write actions until
that governance wiring exists as its own increment. A test in
`test_phase11_services.py` (`test_no_write_actions_exposed`) pins this.

## Provider Platform (Phase 9)

See `backend/providers/` module docstrings and `llm_router.py` (kept as a
backward-compatible facade). Routing: coding → `qwen2.5-coder`, reasoning →
`deepseek-r1`, planning → `phi4`, conversation → `gemma2`, general →
`qwen2.5`, cloud fallback → Gemini, last resort → offline rule-based.

## Plugin Platform (Phase 10)

See `docs/PLUGIN_SDK.md` for the full authoring guide. Permission gating is
capability-based access control (a plugin can only use a permission it
declared *and* was granted) — it is not OS-level process isolation; that
remains future work under Milestone "Security."

## Testing

| Suite | Scope |
|---|---|
| `test_phase9_providers.py` | Provider platform (81 tests) |
| `test_phase10_plugins.py` | Plugin platform (79 tests) |
| `test_phase11_services.py` | Service layer (70 tests) |

All three run fully offline (faked transports/backends) and never mutate
`database/aisha.db`. Combined with the pre-existing phase 2–8 suites, the
full regression set is ~1,368 tests; the only non-passing case anywhere in
the codebase is a pre-existing Windows-only `win32clipboard` test in Phase 8,
unrelated to Phases 9–11.

## What's NOT in this layer (by design)

- Computer control / desktop automation actions (Milestone 2) — governance
  must be wired first.
- REST API exposure of the service layer (Milestone 5 in the brief) — the
  services exist; new Quart routes calling them are the next increment.
- Electron UI consuming any of this — no frontend work has been done in
  Phases 9–11.
- Encrypted secrets / plugin signing (Milestone "Security").
- Packaging (installer, updater, portable mode).

These are documented here rather than silently deferred so the project's true
completion state stays legible.
