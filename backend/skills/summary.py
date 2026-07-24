"""
Summary Skill — Priority 7.

Generates daily summaries from memory data.
"""

from __future__ import annotations

import re

from skills.base import BaseSkill, SkillContext
from core.skill_registry import registry

# Import existing summary logic
from notifications import generate_daily_summary, is_summary_command

_SUMMARY_PATTERNS = [
    re.compile(r"\b(daily summary|summarize|summarise|my day|today'?s summary|end of day)\b", re.I),
]


class SummarySkill(BaseSkill):
    name = "summary"
    priority = 7

    def can_handle(self, user_input: str, context: SkillContext) -> bool:
        return any(p.search(user_input) for p in _SUMMARY_PATTERNS)

    def handle(self, user_input: str, context: SkillContext) -> str:
        return generate_daily_summary(context.memory)


registry.register(SummarySkill())
