"""
Base Skill Interface for Aisha AI Assistant.

All skills must subclass ``BaseSkill`` and implement:
  - ``can_handle(user_input, context)`` → bool
  - ``handle(user_input, context)`` → str

Skills self-register by calling ``SkillRegistry.register()``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SkillContext:
    """
    Shared context passed to every skill's can_handle / handle methods.

    Holds pre-computed data from the brain's Phase 1 (context gathering).
    """

    __slots__ = (
        "emotion", "emotion_cause", "response_style",
        "role_match", "profile_updates", "memory",
    )

    def __init__(
        self,
        emotion: str = "neutral",
        emotion_cause: str | None = None,
        response_style: str = "normal",
        role_match: Any = None,
        profile_updates: list[str] | None = None,
        memory: Any = None,
    ):
        self.emotion = emotion
        self.emotion_cause = emotion_cause
        self.response_style = response_style
        self.role_match = role_match
        self.profile_updates = profile_updates or []
        self.memory = memory


class BaseSkill(ABC):
    """
    Abstract base class for all Aisha skills.

    Attributes
    ----------
    name : str
        Short identifier (e.g. "reminder", "emotion").
    priority : int
        Lower number = higher priority (checked first).
    """

    name: str = "unnamed"
    priority: int = 100  # default: very low priority

    @abstractmethod
    def can_handle(self, user_input: str, context: SkillContext) -> bool:
        """Return True if this skill should handle the given input."""
        ...

    @abstractmethod
    def handle(self, user_input: str, context: SkillContext) -> str:
        """Process the input and return a response string."""
        ...

    def __repr__(self) -> str:
        return f"<Skill:{self.name} priority={self.priority}>"
