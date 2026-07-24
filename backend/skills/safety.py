"""
Safety Skill — Priority 1.

Intercepts crisis keywords and provides immediate safety responses.
Overrides all other handlers. Keyword set matches brain.py legacy exactly.
"""

from __future__ import annotations

from skills.base import BaseSkill, SkillContext
from core.skill_registry import registry

# Full keyword set from brain.py (merged with original skill set)
_SAFETY_KEYWORDS: frozenset[str] = frozenset({
    "kill myself", "want to die", "end my life", "suicide",
    "self harm", "self-harm", "hurt myself",
    "end it all", "no reason to live",
    "don't want to live", "don't want to be alive",
})

_SAFETY_RESPONSE: str = (
    "I hear you, and I want you to know that you're not alone. "
    "Please talk to someone who can help.\n\n"
    "📞 **AASRA (India):** 9820466726\n"
    "📞 **iCall:** 9152987821\n"
    "📞 **Vandrevala Foundation:** 1860-2662-345 (24/7)\n"
    "📞 **International:** https://findahelpline.com\n\n"
    "You matter. I'm here for you."
)


class SafetySkill(BaseSkill):
    name = "safety"
    priority = 1

    def can_handle(self, user_input: str, context: SkillContext) -> bool:
        lower = user_input.lower()
        return any(kw in lower for kw in _SAFETY_KEYWORDS)

    def handle(self, user_input: str, context: SkillContext) -> str:
        return _SAFETY_RESPONSE


# Auto-register
registry.register(SafetySkill())
