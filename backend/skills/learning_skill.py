"""
Learning Skill — Priority 8.

Delegates to the existing learning module.
"""

from __future__ import annotations

from skills.base import BaseSkill, SkillContext
from core.skill_registry import registry
from learning import is_learning_command, handle_learning_command


class LearningSkill(BaseSkill):
    name = "learning"
    priority = 8

    def can_handle(self, user_input: str, context: SkillContext) -> bool:
        return is_learning_command(user_input)

    def handle(self, user_input: str, context: SkillContext) -> str:
        return handle_learning_command(user_input, context.memory)


registry.register(LearningSkill())
