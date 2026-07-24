"""
Reminder Skill — Priority 4.

Delegates to the existing scheduler module.
"""

from __future__ import annotations

from skills.base import BaseSkill, SkillContext
from core.skill_registry import registry
from scheduler import is_reminder_command, handle_reminder_input


class ReminderSkill(BaseSkill):
    name = "reminder"
    priority = 4

    def can_handle(self, user_input: str, context: SkillContext) -> bool:
        return is_reminder_command(user_input)

    def handle(self, user_input: str, context: SkillContext) -> str:
        return handle_reminder_input(user_input)


registry.register(ReminderSkill())
