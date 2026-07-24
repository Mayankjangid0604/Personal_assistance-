"""
Recall Skill — Priority 10.

Returns conversation history when the user asks what they said before.
Pattern set matches brain.py legacy exactly.
"""

from __future__ import annotations

import re

from skills.base import BaseSkill, SkillContext
from core.skill_registry import registry

# Exact patterns from brain.py's RECALL_PATTERNS
_RECALL_RE = re.compile(
    r"\b(what did i say|show history|last conversation|recent conversation"
    r"|previous chat|chat history|remember what|what we talked)\b",
    re.IGNORECASE,
)


class RecallSkill(BaseSkill):
    name = "recall"
    priority = 10

    def can_handle(self, user_input: str, context: SkillContext) -> bool:
        return bool(_RECALL_RE.search(user_input))

    def handle(self, user_input: str, context: SkillContext) -> str:
        if not context.memory:
            return "We haven't talked yet! This is our first conversation."

        conversations = context.memory.get_recent_conversations()
        if not conversations:
            return "We haven't talked yet! This is our first conversation."

        lines = ["Recent Conversations:\n"]
        for i, entry in enumerate(conversations, 1):
            lines.append(f"  {i}. User  : {entry.user_input}")
            lines.append(f"     Aisha : {entry.response}")
            lines.append("")  # blank line between entries

        return "\n".join(lines).rstrip()


registry.register(RecallSkill())
