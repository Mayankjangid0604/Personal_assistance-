"""
Power Tools Skill — Priority 9.

Delegates to the existing power_tools module.
"""

from __future__ import annotations

from skills.base import BaseSkill, SkillContext
from core.skill_registry import registry
from power_tools import is_power_command, handle_power_command


class PowerSkill(BaseSkill):
    name = "power"
    priority = 9

    def can_handle(self, user_input: str, context: SkillContext) -> bool:
        return is_power_command(user_input)

    def handle(self, user_input: str, context: SkillContext) -> str:
        return handle_power_command(user_input)


registry.register(PowerSkill())
