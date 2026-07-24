"""
Task Skill — Priority 3.

Delegates to the existing task_executor module for system commands.
"""

from __future__ import annotations

from skills.base import BaseSkill, SkillContext
from core.skill_registry import registry

# Reuse existing task execution logic
from task_executor import is_task_command, execute_task


class TaskSkill(BaseSkill):
    name = "task"
    priority = 3

    def can_handle(self, user_input: str, context: SkillContext) -> bool:
        if not is_task_command(user_input):
            return False
        # Double-check: actually attempt execution to confirm it's real
        result = execute_task(user_input)
        if result and result.detected:
            # Stash the result so handle() doesn't re-execute
            self._last_result = result
            return True
        return False

    def handle(self, user_input: str, context: SkillContext) -> str:
        result = getattr(self, "_last_result", None)
        if result and result.detected:
            self._last_result = None  # consume
            return result.message
        # Fallback: re-execute (should not normally reach here)
        result = execute_task(user_input)
        if result and result.detected:
            return result.message
        return "I tried to run that task, but it didn't work as expected."


registry.register(TaskSkill())
