"""
General Skill — Priority 100 (lowest / fallback).

Routes to the LLM (Gemini) with context, falls back to rule-based
response generator if the LLM call fails.
"""

from __future__ import annotations

from skills.base import BaseSkill, SkillContext
from core.skill_registry import registry

from llm_router import generate_ai_response
from response_generator import generate_response
from power_tools import get_extended_context


class GeneralSkill(BaseSkill):
    name = "general"
    priority = 100  # catch-all — always last

    def can_handle(self, user_input: str, context: SkillContext) -> bool:
        return True  # always matches as fallback

    def handle(self, user_input: str, context: SkillContext) -> str:
        user_name = "User"
        if context.memory:
            user_name = context.memory.get_user_info("name") or "User"

        role = context.role_match.role if context.role_match else "assistant"

        llm_context = {
            "user_name": user_name,
            "emotion": context.emotion,
            "role": role,
            "chat_history": get_extended_context(context.memory, limit=10) if context.memory else [],
        }

        try:
            return generate_ai_response(user_input, llm_context)
        except Exception:
            result = generate_response(user_input, role)
            return result.response


registry.register(GeneralSkill())
