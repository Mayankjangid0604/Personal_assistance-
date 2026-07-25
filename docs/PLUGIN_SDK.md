# AISHA Plugin SDK

**Phase 10 — Plugin Platform** · `backend/plugins/`

The plugin platform lets you extend AISHA with new, permission-gated, hot-loadable
capabilities without touching the core. It mirrors the provider platform: a
**registry** for discovery, a **manager** for lifecycle, a **permission broker**
for access control, and **health monitoring** throughout. Every plugin describes
itself with a **manifest** and returns results in a uniform shape.

> **Security note.** Permission gating here is *capability-based access control*
> — a plugin can only exercise a privilege it declared *and* was granted. It is
> the integration seam for Milestone 2's deeper governance (Human Oversight /
> Automation Governor / Audit). It is **not** OS-level process isolation; true
> sandboxing (subprocess isolation, seccomp) is future work.

---

## 1. Quick start

```python
from plugins import build_default_manager

mgr = build_default_manager()          # registers + loads the built-in catalogue
print(mgr.invoke("calculator", "evaluate", "2 + 2 * 10").data)   # -> 22
print(mgr.capability_index())          # {capability: [plugin names]}
print(mgr.health_report())             # per-plugin health
```

## 2. Writing a plugin

The fastest path is `SimplePlugin` + the `@action` decorator. Implement
`manifest()` and mark your action methods.

```python
from plugins.sdk import SimplePlugin, action
from plugins.base import PluginManifest, Capability, Permission, HealthState

class GreeterPlugin(SimplePlugin):
    def manifest(self):
        return PluginManifest(
            name="greeter",                       # lowercase, [a-z0-9_-], 2-40 chars
            version="1.0.0",                      # semver x.y.z
            capabilities=[Capability.SYSTEM],
            permissions=[Permission.SYSTEM_INFO], # what you may need
            description="Greets a user.",
            documentation="actions: greet(name)",
            dependencies=[],                      # e.g. ["calculator>=1.0.0"]
        )

    @action
    def greet(self, name="world"):
        self.require(Permission.SYSTEM_INFO)      # enforced by the broker
        return f"hello {name}"

    def health(self):                             # optional; default = healthy
        return self.health_of(HealthState.HEALTHY, "ready")
```

Register and use it:

```python
from plugins import PluginManager
mgr = PluginManager()
mgr.register(GreeterPlugin())     # validated on registration
mgr.load("greeter")               # activate()
mgr.invoke("greeter", "greet", "Mayank").data   # -> "hello Mayank"
```

### Returning results

An action may return a **bare value** (wrapped in `PluginResult.success`) or an
explicit `PluginResult`:

```python
from plugins.base import PluginResult

@action
def risky(self):
    if not ok:
        return PluginResult.failure("could not do the thing")
    return PluginResult.success({"done": True})
```

`invoke()` **never raises** — errors (including `PermissionDenied`) come back as
`PluginResult(ok=False, error=...)`.

## 3. The manifest

| Field | Meaning |
|---|---|
| `name` | Unique id, `^[a-z][a-z0-9_-]{1,39}$` |
| `version` | Semver `x.y.z` |
| `capabilities` | `list[Capability]` — used for discovery / the capability index |
| `permissions` | `list[Permission]` — the privileges the plugin may request |
| `dependencies` | `["other>=1.2.0", ...]` — resolved into load order |
| `description` / `documentation` | Human-readable text surfaced in the manager UI |
| `config_schema` | Free-form description of expected config keys |
| `tags` | Discovery hints |

Manifests are validated on `register()`; invalid manifests raise `ValidationError`.

## 4. Permissions

Declare what you may need in the manifest, then call `self.require(perm)` before
each privileged operation. The manager grants declared permissions automatically
by default (`manager.auto_grant = True`); set it to `False` to grant explicitly:

```python
mgr.auto_grant = False
mgr.load("greeter")
mgr.broker.grant("greeter", Permission.SYSTEM_INFO)   # only this is now allowed
```

Available permissions: `fs.read`, `fs.write`, `clipboard.read`, `clipboard.write`,
`process.spawn`, `process.kill`, `network`, `system.info`, `system.control`,
`screen.capture`, `device.camera`, `device.microphone`, `system.notify`.

Attempting an operation whose permission was not granted raises `PermissionDenied`
internally and returns a failed `PluginResult`. Grant/revoke/check decisions can
be routed to an audit sink via `PermissionBroker(audit=callback)`.

## 5. Lifecycle

```
register() → DISCOVERED
   load()  → ACTIVE        (validates deps, grants perms, calls activate)
 unload()  → UNLOADED      (calls deactivate, revokes perms)
 reload()  → hot reload    (unload + load; picks up new config)
disable()  → DISABLED  /  enable() → ACTIVE
```

- `load_all()` loads everything in **dependency order** (topological sort).
- Unmet or version-incompatible dependencies put a plugin into `ERROR` with a
  message available via `manager.error(name)`.
- `manager.status_report()` and `manager.health_report()` give fleet-wide views.

## 6. Configuration

Config is per-plugin and injected at activation:

```python
mgr.config.set("filesystem", {"roots": ["/home/user/Documents"]})
mgr.reload("filesystem")          # picks up the new config
# inside the plugin:
self.config("roots", default=["."])
```

`PluginConfigStore(path=...)` adds JSON persistence (`save_file()` / `load_file()`).

## 7. Built-in catalogue

**Implemented & tested (offline):**

| Plugin | Capability | Permissions | Notes |
|---|---|---|---|
| `calculator` | calculator | — | Safe AST arithmetic; no `eval` |
| `filesystem` | filesystem | fs.read, fs.write | Path-jailed to configured roots |
| `clipboard` | clipboard | clipboard.read/write | OS backend injectable; memory fallback |
| `system_info` | system | system.info | Read-only host info |
| `git` | git | process.spawn | Read-only git via argv (no shell) |

**Declared but not yet implemented** (report `unavailable`, ready to fill in):
`terminal`, `browser`, `pdf`, `ocr`, `weather`, `calendar`, `email`, `camera`,
`microphone`, `image_generation`.

## 8. Testing your plugin

Inject fakes for anything external (see the built-ins for patterns — the git
plugin takes a `runner`, the clipboard plugin takes backend callables). A minimal
test:

```python
mgr = PluginManager()
mgr.register(GreeterPlugin()); mgr.load("greeter")
assert mgr.invoke("greeter", "greet", "x").data == "hello x"
```

The platform's own suite lives in `backend/tests/test_phase10_plugins.py`
(79 tests). Run it with `python backend/tests/test_phase10_plugins.py`.

## 9. Design principles

- **Self-describing** — everything the UI needs is in the manifest.
- **Least privilege** — nothing runs without a declared, granted permission.
- **Never crash the caller** — actions return `PluginResult`, never exceptions.
- **Injectable I/O** — external effects go through injectable backends for testability.
- **Config-driven, no hardcoding** — discovery is by capability, not by name.
