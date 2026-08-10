# AISHA — Project Audit Report

**Date:** 2026-08-10 · **Scope:** full repository (backend, frontend, Electron, database, tests, master plan)

---

## 1. Executive summary

Aisha is a personal AI assistant with a Python/Quart backend (~35,000 lines, 68 modules), a React 19 + Electron frontend, SQLite persistence (55 tables), and Google Gemini (`gemini-2.0-flash`) as the LLM. The repo follows a 7-phase master plan; the code claims to implement "phases 1–8."

**The honest current stage: a solid, working Phase 1–2 core wrapped in a very large Phase 3–8 layer that is mostly bookkeeping and templates — and, critically, none of it influences what Aisha actually says.** Every "cognitive" module runs *after* the LLM answer is generated and only writes metadata to the database. The prompt sent to Gemini contains only: user name, detected emotion, role, and the last 3 turns.

**Verdict by the numbers:**

| Metric | Value |
|---|---|
| Python code | ~35,000 lines / 68 backend modules / 13 skills |
| HTTP routes | ~120 — the frontend uses **9** of them |
| SQLite tables | 55 — repositories exist for only 7 domains |
| Tests | 310 collected · 297 pass · 13 fail (missing deps) · 2 files break pytest collection |
| Frontend panels | 6 — all real API data, all read-only except chat |
| Git history | 1 commit ("Initial commit") |

---

## 2. Current stage vs. the master plan

| Plan phase | Goal | Actual status |
|---|---|---|
| **1 — Foundation** | Modular skills, markdown, streaming, notifications | ✅ **Done and real.** Skill registry with priorities works; markdown chat works; native notifications wired (broken icon path). |
| **2 — Real AI experience** | Voice pipeline, streaming, sessions | ⚠️ **Partial.** SSE endpoint exists but *buffers the whole response* before emitting (fake streaming) and calls Gemini **twice** per message. Two voice pipelines exist (backend pyttsx3/SpeechRecognition, frontend Web Speech API) — neither works: backend is server-side-mic desktop code, frontend Web Speech is non-functional inside Electron. |
| **3 — Memory evolution** | SQLite, embeddings, episodic memory | ⚠️ **Partial.** SQLite migration is genuinely done. But "semantic memory" is hand-rolled **TF-IDF over a 256-word vocabulary**, not embeddings — recall is near-lexical. Only the last 20 conversation turns are ever kept. |
| **4 — Desktop AI system** | Desktop awareness, automation | 🪟 **Windows-only, currently inert.** All Win32 calls silently return empty off-Windows, so every downstream feature (focus score, workflow intelligence, routines) computes on a constant empty snapshot. `focus_mode` actions are no-op stubs that report success. |
| **5 — Autonomous AI** | Proactive, adaptive | ⚠️ **Framework without fuel.** Routine/pattern tables have 0 rows; reflections are `random.choice` from templates; a latent `NameError` (`conversation_engine.py:299` vs `:304`) silently kills the whole Phase 5 block off-Windows. The autonomous nudge loop only runs from the legacy terminal app, never from the server. |
| **6 — Production level** | Settings, security, logging, testing | ❌ **Not started in practice.** No auth on any endpoint, CORS wide open, `debug=True` on `0.0.0.0`, no settings UI, no logging framework (print + ~100 `except: pass`), tests write into the production database. |
| **7 — Future platform** | Multi-agent, plugins | 🎭 **Simulated.** The 6 "sandboxed agents" are if/elif rules over SQL; `brainstorm` returns `random.sample` of static SCAMPER prompts; `generate_summary` picks the longest sentence; `explain_action` is f-string templating over the audit row; `forecast_milestones` uses a hardcoded velocity of 0.02. |

**What is genuinely well-built:** the SQLite schema and WAL setup, the skill registry, the Gemini key-rotation router, the human-oversight permission/audit/rollback framework (real, DB-backed, with working undo handlers), the knowledge-graph structure, and the frontend's WebSocket hook and orb error-boundaries.

---

## 3. The core architectural problem

```
user message
   └─► brain.process_input()        ◄── LLM answers HERE (context: name, emotion, role, last 3 turns)
          └─► response text final
                └─► Phases 3–8 run AFTER the answer:
                    semantic recall, cognitive agents, personality modifiers,
                    project context, knowledge graph, behavioral model …
                    → written to SQLite + returned as JSON metadata
                    → NEVER injected into the prompt
```

- `cognitive_context["system_prompt"]` is assembled (`conversation_engine.py:200-204`) and **never used anywhere**.
- `deep_personalization.get_prompt_modifiers()` returns a modifier string that is **never sent to the LLM**.
- The single highest-leverage change in the entire project is moving this computation *before* the LLM call and injecting it into the prompt. That one refactor converts ~20 modules from decorative to functional.

---

## 4. Critical issues (ranked)

### 🔴 P0 — Safety: profile extraction stores and replays self-harm text
`brain.py:149-154` — the goal-extraction regex `r"\bi want to\s+(.+)"` runs **before** the safety skill. Input like "I want to kill myself…" is stored as the user's *goal* even though the safety skill then responds with helpline text. `autonomous.py:178-200` later replays it: *"By the way, you mentioned you wanted to {goal}. Want to continue?"* — spoken aloud in voice mode. Profile extraction must be gated behind the safety check, and stored goals sanitized.

### 🔴 P0 — Personal data committed to git
`database/aisha.db` (1.1 MB, 52 populated tables) is tracked. It contains real conversations (including the crisis message above), reminders, behavioral logs, and hundreds of rows of test residue — because **tests run against the production DB path** with no fixture isolation. `.gitignore` excludes the old JSON files but not the SQLite file that replaced them. Remove from git, add to `.gitignore`, and purge history (`git filter-repo`).

### 🔴 P0 — Security baseline absent
- No authentication on ~120 endpoints; CORS allows all origins; `app.run(host="0.0.0.0", port=5000, debug=True)`.
- `/continuity/export` + `/continuity/import` accept **arbitrary filesystem paths** (arbitrary file write/read).
- `/executor/action` accepts `auto_approve` from the request body — an unauthenticated POST can bypass the confirmation queue and reach `subprocess.Popen(..., shell=True)`.
- "Delete all my data" wipes only 15 of ~55 tables while telling the user *"All your data has been cleared."*
- Encrypted export **silently falls back to plaintext** when `cryptography` is missing and still reports success.

### 🟠 P1 — `/chat/stream` calls Gemini twice and doesn't stream
`server.py:235` runs the full pipeline (one Gemini call), then `:271` makes a **second** streaming call — and materializes the entire generator before emitting, so nothing actually streams. It also persists the conversation twice (doubled rows and behaviour counters).

### 🟠 P1 — Electron shell likely won't start
`package.json` has `"type": "module"` while `electron/main.js` and all preloads are CommonJS → `require is not defined` under Electron 35. Also: `dev:electron` uses Windows-only `set` syntax; the notification icon points to a non-existent file; mini-window mic/mute buttons send IPC that nothing handles; no tray despite `skipTaskbar` overlays; no packaging config (electron-builder/forge) at all.

### 🟠 P1 — requirements.txt incomplete
`numpy` (hard import in `semantic_memory.py`), `cryptography`, `psutil`, `pywin32`, `pyaudio` are imported but unlisted. A clean `pip install -r requirements.txt` cannot start the server.

### 🟡 P2 — Test hygiene
7 of 12 backend test files are print-based scripts with **zero assert statements**; two break pytest collection outright (module-level `sys.exit`). No `conftest.py`, no CI, no DB fixture — every test run mutates `aisha.db`.

### 🟡 P2 — Frontend/backend drift
Frontend knows 6 handler modes, backend has 11 — `reminder`, `journal`, `summary`, `recall`, `data_control` all display as "General". The backend's full autonomy-approval surface (`/autonomy/pending|approve|reject|audit|rollback`) — arguably its best feature — has **no UI at all**. Panels swallow fetch errors into "no data yet" empty states.

### 🟡 P2 — Concurrency/state bugs
`TaskSkill.can_handle()` *executes* the task to decide if it can handle it, and stashes the result on a shared singleton (race under concurrent requests; a predicate can trigger `shutdown /s /t 60`). `data_control` uses a module-global pending-delete flag shared across all sessions. Stale-closure bug lets voice input fire mid-response (`App.jsx:76-93`).

---

## 5. What to remove

**Dead code (no callers):**
- `backend/planning_engine.py` — no route, no caller (only a test imports it)
- `backend/async_voice.py`, `backend/server_compat.py` — test-only
- `database/migrate_json_to_sqlite.py` — one-shot migration, done
- `main.py` + `backend/voice.py` + `backend/autonomous.py` — a parallel terminal app that duplicates the server with drift; either delete or explicitly demote to a debug tool
- Duplicate `Memory()` singleton in `database/memory.py:237`
- `.pytest_cache/` at repo root

**Frontend boilerplate & dead paths:**
- `frontend/README.md` (unmodified Vite template), `src/assets/react.svg`, `vite.svg`, `hero.png`, `public/icons.svg` — all unreferenced
- Unused imports in `ChatPanel.jsx`; dead IPC channels (`mini:handler`, `mic:deactivate`, unhandled `mic-toggle`/`voice-mute`); unused `send`/`sendTyping`/`onChatResponse` in `useWebSocket` (or actually wire them)

**Duplicated logic (keep one copy):**
- `detect_response_style` (brain.py + emotion_engine.py)
- Safety keywords/responses (skills/safety.py + a *different* hardcoded copy in brain.py)
- Recall regex (skills/recall.py + skills/emotion.py)
- LLM context construction (skills/general.py + server.py)
- Six near-identical `/…/status` endpoints → one `/status`

**Simulated "intelligence" to cut or clearly mark experimental** (they currently create the impression of capability that isn't there): `creative_collaboration` (random SCAMPER), `knowledge_synthesis.generate_summary` (longest sentence), `explainable_autonomy` (f-string narration), `project_evolution` (hardcoded velocity), `cross_app_context` suggestions (`random.choice`), template-driven `reflective_cognition`. Recommendation: collapse phases 5–8 into 2–3 honest modules and reintroduce features when they have real implementations — likely a net deletion of 8,000–10,000 lines that would make the codebase dramatically easier to evolve.

---

## 6. What to add (priority order)

1. **Feed the computed context into the prompt.** Move semantic recall, personality modifiers, project context, and the assembled `system_prompt` *before* the Gemini call and inject them. One refactor; transforms the whole system.
2. **Security baseline.** Token auth middleware, CORS allowlist, remove `debug/0.0.0.0` (use hypercorn), remove arbitrary-path export/import, remove `auto_approve` from the request body, fix delete-all coverage, make encrypted export fail loudly.
3. **Fix streaming.** One Gemini call per message, real chunk-by-chunk async streaming, single persistence write.
4. **Project hygiene.** Root `README.md` (setup/run for backend, frontend, Electron), `.env.example`, complete `requirements.txt` (with a `[windows]` extra for pywin32/psutil), `LICENSE`.
5. **Real embeddings.** Replace 256-word TF-IDF with sentence-transformers + a vector store (the master plan already names ChromaDB). Add memory summarization so history isn't capped at 20 turns.
6. **Test overhaul + CI.** Convert script-tests to pytest with asserts, `conftest.py` with a temp-DB fixture (`DB_PATH` env override), GitHub Actions running pytest + `npm run lint` + `npm run build`.
7. **Frontend catch-up.** Fix the ESM/CJS Electron break; electron-builder packaging; sync the handler map (11 modes); a Settings panel (`/profile`, `/personality`, `/reset` already exist); an **Autonomy approval inbox** for the pending/approve/reject/audit/rollback API; make Habits/Journal/Schedule write-capable; real error states; env-based `API_URL`.
8. **One voice pipeline.** Per the plan: faster-whisper STT + Piper TTS server-side, audio transported over the existing WebSocket — delete both current non-working paths.
9. **Cross-platform task executor.** Abstract the Windows-only app registry behind a platform layer (or explicitly declare Windows-only support).
10. **Logging.** Replace `print` + ~100 blanket `except Exception: pass` with the `logging` module; the silent-failure pattern is why the Phase-5 `NameError` was never noticed.

---

## 7. Suggested 4-week sequence

- **Week 1 — Stop the bleeding:** P0 fixes (safety-gated extraction, purge `aisha.db` from git, auth + CORS + debug off), complete requirements.txt, root README, `.env.example`.
- **Week 2 — Make the intelligence real:** prompt-injection refactor (#1), fix `/chat/stream` (#3), delete dead code (§5), collapse duplicated logic.
- **Week 3 — Trust the code:** pytest conversion + temp-DB fixture + CI; fix Electron startup + packaging; handler-map sync.
- **Week 4 — Visible wins:** Settings panel, autonomy approval inbox, write-capable panels, embeddings spike.

---

*Full details behind every claim in this report carry file:line references gathered from direct code inspection on branch `claude/project-report-review-qz3p3j`.*
