"""
Journal Skill — Priority 6.

Delegates to the existing journal module.
"""

from __future__ import annotations

from skills.base import BaseSkill, SkillContext
from core.skill_registry import registry
from notifications import is_journal_command, handle_journal_command


class JournalSkill(BaseSkill):
    name = "journal"
    priority = 6

    def can_handle(self, user_input: str, context: SkillContext) -> bool:
        return is_journal_command(user_input)

    def handle(self, user_input: str, context: SkillContext) -> str:
        return handle_journal_command(user_input, context.memory)


registry.register(JournalSkill())
