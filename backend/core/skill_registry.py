"""
Skill Registry for Aisha AI Assistant.

Manages dynamic registration and priority-ordered dispatch of skills.
Skills self-register by calling ``SkillRegistry.register(skill_instance)``.

Usage::

    from core.skill_registry import registry

    # Skills register themselves on import
    result = registry.dispatch(user_input, context)
"""

from __future__ import annotations

import logging
from typing import Any

from skills.base import BaseSkill, SkillContext

_log = logging.getLogger("aisha.registry")


class SkillRegistry:
    """
    Central registry that holds all skill instances sorted by priority.

    Skills are dispatched in priority order: the first skill whose
    ``can_handle()`` returns True gets to ``handle()`` the request.
    """

    def __init__(self) -> None:
        self._skills: list[BaseSkill] = []
        self._sorted = True

    def register(self, skill: BaseSkill) -> None:
        """Register a skill instance. Can be called at import time."""
        self._skills.append(skill)
        self._sorted = False
        _log.info("Registered skill: %s (priority=%d)", skill.name, skill.priority)

    def _ensure_sorted(self) -> None:
        if not self._sorted:
            self._skills.sort(key=lambda s: s.priority)
            self._sorted = True

    @property
    def skills(self) -> list[BaseSkill]:
        """Return all registered skills in priority order."""
        self._ensure_sorted()
        return list(self._skills)

    def dispatch(self, user_input: str, context: SkillContext) -> tuple[str, str]:
        """
        Route input to the highest-priority matching skill.

        Parameters
        ----------
        user_input : str
            Raw user text.
        context : SkillContext
            Pre-computed context (emotion, role, memory, etc.).

        Returns
        -------
        tuple[str, str]
            (handler_name, response_text).
            Returns ("general", "") if no skill matched.
        """
        self._ensure_sorted()

        for skill in self._skills:
            try:
                if skill.can_handle(user_input, context):
                    response = skill.handle(user_input, context)
                    _log.debug("[DISPATCH] %s handled input", skill.name)
                    return (skill.name, response)
            except Exception as exc:
                _log.error("[DISPATCH] %s raised: %s", skill.name, exc)
                continue

        return ("general", "")

    def get_skill(self, name: str) -> BaseSkill | None:
        """Retrieve a skill by name."""
        for s in self._skills:
            if s.name == name:
                return s
        return None

    def __len__(self) -> int:
        return len(self._skills)

    def __repr__(self) -> str:
        self._ensure_sorted()
        names = [f"{s.name}({s.priority})" for s in self._skills]
        return f"<SkillRegistry [{', '.join(names)}]>"


# Singleton instance — import this from skills
registry = SkillRegistry()
