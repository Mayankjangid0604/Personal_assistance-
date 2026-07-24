"""
Aisha Skills Package.

Each skill module auto-registers itself with the SkillRegistry on import.

Auto-discovery: Every ``.py`` file in this directory (except ``__init__``,
``base``, and files starting with ``_``) is imported automatically when
``import skills`` runs.  This means dropping a new skill file into the
``skills/`` folder is all that's needed to activate it — no manual import
list required.
"""

import importlib
import os
import sys

# ---------------------------------------------------------------------------
# Path setup — skills need access to backend/ and database/ siblings
# ---------------------------------------------------------------------------
_SKILLS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_SKILLS_DIR)
_DATABASE_DIR = os.path.join(os.path.dirname(_BACKEND_DIR), "database")

for _p in (_BACKEND_DIR, _DATABASE_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------------------
# Dynamic skill auto-discovery
# ---------------------------------------------------------------------------

# Files to skip (not skills)
_SKIP = {"__init__", "base"}


def _auto_discover_skills() -> list[str]:
    """
    Import every skill module in the ``skills/`` directory.

    Scans for ``.py`` files that are not in the skip list and do not
    start with ``_``.  Each imported module's top-level code runs its
    ``registry.register(...)`` call, completing self-registration.

    Returns the list of module names that were imported.
    """
    loaded: list[str] = []

    for filename in sorted(os.listdir(_SKILLS_DIR)):
        if not filename.endswith(".py"):
            continue
        module_name = filename[:-3]  # strip .py
        if module_name in _SKIP or module_name.startswith("_"):
            continue

        fqn = f"skills.{module_name}"
        try:
            importlib.import_module(fqn)
            loaded.append(module_name)
        except Exception as exc:
            # Never crash the entire app because one skill failed to load
            print(f"  [Skills] WARN: Failed to load {fqn}: {exc}")

    return loaded


# Run auto-discovery on first import
_loaded_skills = _auto_discover_skills()
