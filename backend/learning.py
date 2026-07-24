"""
Learning Intelligence System for Aisha AI Assistant.

Provides five capabilities:

1. **Interest Tracking**   -- Detects and counts repeated topics from
   every conversation to build a user interest profile.

2. **Skill Practice**      -- Generates practice tasks when the user
   wants to learn a specific skill or subject.

3. **Learning Suggestions** -- Recommends next topics based on the
   user's conversation history and tracked interests.

4. **Milestone Planning**  -- Breaks a goal into concrete steps and
   milestones with a progress tracker.

5. **Contextual Learning** -- Uses past conversations to personalise
   all of the above.

Supported commands::

    "I want to learn Python"
    "practice Python"
    "give me practice tasks"
    "what should I learn next"
    "suggest something to learn"
    "show my interests"
    "create a learning plan for AI"
    "show my learning plan"
    "my progress"

Usage::

    from learning import (
        is_learning_command, handle_learning_command,
        track_topics,
    )
"""

from __future__ import annotations

import json
import random
import re
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# SQLite Repository
# ---------------------------------------------------------------------------

import sys as _sys
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_PROJECT_ROOT))

from database.repositories import learning_repo

# In-memory cache (kept in sync with SQLite on every write)
_data: dict[str, Any] = {
    "interests": {},         # topic -> count
    "practice_log": [],      # completed practice items
    "milestones": [],        # active learning plans
}


def _load() -> None:
    """Load data from SQLite into in-memory cache."""
    _data["interests"] = learning_repo.get_all_interests()
    _data["practice_log"] = learning_repo.get_practice_log()
    _data["milestones"] = learning_repo.get_all_plans()
    print(f"  [Learning] Loaded from SQLite ({len(_data['interests'])} interests, "
          f"{len(_data['milestones'])} plans)")


def _save_interests() -> None:
    """Sync interests cache to SQLite."""
    for topic, count in _data["interests"].items():
        learning_repo.save_interest(topic, count)


_load()


# ═══════════════════════════════════════════════════════════════════════════
#  1. INTEREST TRACKING
# ═══════════════════════════════════════════════════════════════════════════

_TOPIC_KEYWORDS: dict[str, list[str]] = {
    "python":       ["python", "django", "flask", "pip", "pandas"],
    "javascript":   ["javascript", "js", "react", "node", "vue", "next"],
    "ai":           ["ai", "artificial intelligence", "machine learning", "ml",
                     "deep learning", "neural", "llm", "gpt", "model"],
    "web":          ["html", "css", "frontend", "backend", "api", "rest",
                     "website", "web dev", "web development"],
    "data science": ["data science", "data analysis", "statistics",
                     "visualization", "dataset", "csv"],
    "database":     ["database", "sql", "mongo", "mysql", "postgres", "db"],
    "mobile":       ["android", "ios", "flutter", "react native", "mobile app"],
    "devops":       ["docker", "kubernetes", "ci/cd", "devops", "cloud",
                     "aws", "azure", "deployment"],
    "cybersecurity":["security", "hacking", "encryption", "cyber",
                     "penetration", "vulnerability"],
    "dsa":          ["dsa", "data structure", "algorithm", "sorting",
                     "linked list", "tree", "graph", "recursion",
                     "dynamic programming"],
    "math":         ["math", "calculus", "algebra", "linear algebra",
                     "probability", "matrix"],
    "english":      ["english", "grammar", "vocabulary", "writing",
                     "essay", "communication"],
    "career":       ["resume", "interview", "career", "job", "placement",
                     "internship", "portfolio"],
}


def track_topics(user_input: str) -> list[str]:
    """
    Scan user input for known topics and increment interest counters.
    Called on every message (passive tracking).

    Returns a list of detected topic names.
    """
    lower = user_input.lower()
    detected: list[str] = []

    for topic, keywords in _TOPIC_KEYWORDS.items():
        for kw in keywords:
            if re.search(rf"\b{re.escape(kw)}\b", lower):
                _data["interests"][topic] = _data["interests"].get(topic, 0) + 1
                detected.append(topic)
                break  # one match per topic per message

    if detected:
        _save_interests()
    return detected


def get_top_interests(limit: int = 5) -> list[tuple[str, int]]:
    """Return the top N interests sorted by frequency."""
    return Counter(_data["interests"]).most_common(limit)


def _format_interests() -> str:
    """Format interests for display."""
    top = get_top_interests(8)
    if not top:
        return "I haven't tracked any interests yet. Keep chatting and I'll learn what you're into!"

    lines = ["Your top interests (based on our conversations):\n"]
    for i, (topic, count) in enumerate(top, 1):
        bar = "█" * min(count, 15)
        lines.append(f"  {i}. {topic.title():<16} {bar} ({count})")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
#  2. SKILL PRACTICE SYSTEM
# ═══════════════════════════════════════════════════════════════════════════

_PRACTICE_TASKS: dict[str, list[str]] = {
    "python": [
        "Write a function that reverses a string without slicing.",
        "Create a program that counts word frequency in a paragraph.",
        "Build a simple calculator using functions.",
        "Write a script that reads a CSV file and prints the top 5 rows.",
        "Implement a to-do list using a dictionary.",
        "Create a function that checks if a number is prime.",
        "Write a program that generates the Fibonacci sequence up to N.",
    ],
    "javascript": [
        "Create a function that debounces another function.",
        "Build a simple DOM counter with increment/decrement buttons.",
        "Write a fetch() call that handles errors gracefully.",
        "Implement array methods (map, filter, reduce) from scratch.",
        "Create a simple stopwatch using setInterval.",
    ],
    "ai": [
        "Explain the difference between supervised and unsupervised learning.",
        "Build a simple linear regression model using dummy data.",
        "Describe 3 real-world applications of NLP.",
        "Write pseudocode for a basic neural network forward pass.",
        "Compare precision vs recall -- when would you prioritise each?",
    ],
    "web": [
        "Build a responsive navbar using only CSS flexbox.",
        "Create a contact form with client-side validation.",
        "Explain the box model in CSS.",
        "Build a REST API endpoint that returns JSON.",
        "Design a responsive card layout using CSS Grid.",
    ],
    "dsa": [
        "Implement a stack using an array.",
        "Write binary search from scratch.",
        "Solve: reverse a linked list.",
        "Implement BFS on a graph represented as an adjacency list.",
        "Write a function to check balanced parentheses.",
    ],
    "database": [
        "Write a SQL query to find the second highest salary.",
        "Explain the difference between INNER JOIN and LEFT JOIN.",
        "Design a schema for a blog with users, posts, and comments.",
        "Write a MongoDB aggregation pipeline example.",
    ],
}

# Generic tasks for unknown topics
_GENERIC_PRACTICE: list[str] = [
    "Research the top 3 concepts in {topic} and write a short summary of each.",
    "Find a beginner tutorial on {topic} and follow along for 30 minutes.",
    "Explain {topic} to me as if I'm 10 years old (this tests your understanding).",
    "List 5 real-world applications of {topic}.",
    "Create a simple project outline related to {topic}.",
]


def _generate_practice(topic: str) -> str:
    """Generate 3 practice tasks for a topic."""
    key = topic.lower().strip()

    if key in _PRACTICE_TASKS:
        tasks = random.sample(_PRACTICE_TASKS[key], min(3, len(_PRACTICE_TASKS[key])))
    else:
        templates = random.sample(_GENERIC_PRACTICE, 3)
        tasks = [t.format(topic=topic.title()) for t in templates]

    lines = [f"Practice tasks for {topic.title()}:\n"]
    for i, task in enumerate(tasks, 1):
        lines.append(f"  {i}. {task}")

    lines.append(f"\nTry one and tell me your answer -- I'll help if you get stuck!")

    # Log practice
    _data["practice_log"].append({
        "topic": key,
        "count": len(tasks),
        "time": datetime.now().isoformat(timespec="seconds"),
    })
    learning_repo.add_practice_log(key, len(tasks),
                                    datetime.now().isoformat(timespec="seconds"))

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
#  3. LEARNING SUGGESTIONS
# ═══════════════════════════════════════════════════════════════════════════

_LEARNING_PATHS: dict[str, list[str]] = {
    "python":       ["dsa", "web", "ai", "database"],
    "javascript":   ["web", "mobile", "devops"],
    "ai":           ["python", "math", "data science"],
    "web":          ["javascript", "database", "devops"],
    "dsa":          ["python", "javascript", "career"],
    "data science": ["python", "math", "ai", "database"],
    "database":     ["web", "devops", "data science"],
    "mobile":       ["javascript", "database", "devops"],
    "devops":       ["database", "cybersecurity", "web"],
    "cybersecurity":["devops", "python", "database"],
    "math":         ["ai", "data science", "dsa"],
    "english":      ["career", "web"],
    "career":       ["web", "python", "dsa"],
}


def _suggest_next_topics(memory: Any) -> str:
    """Suggest topics based on interests and learning paths."""
    top = get_top_interests(3)

    if not top:
        # No data -- suggest popular starting points
        starters = ["Python", "Web Development", "DSA"]
        lines = ["Since we're just getting started, here are great topics to begin with:\n"]
        for i, s in enumerate(starters, 1):
            lines.append(f"  {i}. {s}")
        lines.append("\nJust say \"I want to learn Python\" to start!")
        return "\n".join(lines)

    known_topics = {t for t, _ in top}
    suggestions: list[str] = []

    for topic, _ in top:
        nexts = _LEARNING_PATHS.get(topic, [])
        for n in nexts:
            if n not in known_topics and n not in suggestions:
                suggestions.append(n)

    if not suggestions:
        suggestions = ["career", "devops", "cybersecurity"]

    suggestions = suggestions[:4]

    lines = [f"Based on your interests ({', '.join(t.title() for t, _ in top)}), I'd suggest:\n"]
    for i, s in enumerate(suggestions, 1):
        lines.append(f"  {i}. {s.title()}")

    lines.append(f"\nSay \"I want to learn {suggestions[0].title()}\" to get started!")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
#  4. MILESTONE PLANNING
# ═══════════════════════════════════════════════════════════════════════════

_MILESTONE_TEMPLATES: dict[str, list[dict[str, str]]] = {
    "python": [
        {"step": "Learn variables, data types, and operators",     "level": "Beginner"},
        {"step": "Master control flow (if/else, loops)",           "level": "Beginner"},
        {"step": "Understand functions and modules",               "level": "Beginner"},
        {"step": "Learn file handling and error handling",          "level": "Intermediate"},
        {"step": "Practice OOP (classes, inheritance)",            "level": "Intermediate"},
        {"step": "Build a mini project (to-do app, calculator)",   "level": "Intermediate"},
        {"step": "Learn a framework (Flask / Django)",             "level": "Advanced"},
        {"step": "Build a full project and deploy it",             "level": "Advanced"},
    ],
    "ai": [
        {"step": "Understand what AI/ML is and its types",         "level": "Beginner"},
        {"step": "Learn Python basics + NumPy/Pandas",             "level": "Beginner"},
        {"step": "Study linear regression and classification",     "level": "Intermediate"},
        {"step": "Learn neural networks and deep learning basics", "level": "Intermediate"},
        {"step": "Practice with real datasets (Kaggle)",           "level": "Intermediate"},
        {"step": "Build an end-to-end ML project",                 "level": "Advanced"},
        {"step": "Study NLP or Computer Vision",                   "level": "Advanced"},
    ],
    "web": [
        {"step": "Learn HTML structure and semantics",             "level": "Beginner"},
        {"step": "Master CSS (flexbox, grid, responsive)",         "level": "Beginner"},
        {"step": "Learn JavaScript fundamentals",                  "level": "Beginner"},
        {"step": "Build a static website from scratch",            "level": "Intermediate"},
        {"step": "Learn a framework (React / Vue)",                "level": "Intermediate"},
        {"step": "Learn backend basics (Node.js / Flask)",         "level": "Advanced"},
        {"step": "Build a full-stack app and deploy it",           "level": "Advanced"},
    ],
    "dsa": [
        {"step": "Learn arrays, strings, and basic operations",    "level": "Beginner"},
        {"step": "Understand linked lists and stacks/queues",      "level": "Beginner"},
        {"step": "Learn sorting and searching algorithms",         "level": "Intermediate"},
        {"step": "Study trees, graphs, and traversals",            "level": "Intermediate"},
        {"step": "Practice dynamic programming",                   "level": "Advanced"},
        {"step": "Solve 100+ problems on LeetCode/HackerRank",    "level": "Advanced"},
    ],
}

# Generic milestone template
_GENERIC_MILESTONES: list[dict[str, str]] = [
    {"step": "Research and understand the fundamentals of {topic}",  "level": "Beginner"},
    {"step": "Follow a structured tutorial or course on {topic}",   "level": "Beginner"},
    {"step": "Practice with small exercises or projects",           "level": "Intermediate"},
    {"step": "Build a mini project applying {topic} concepts",      "level": "Intermediate"},
    {"step": "Tackle an advanced problem or real-world project",    "level": "Advanced"},
    {"step": "Teach {topic} to someone else (best test of mastery)","level": "Advanced"},
]


def _create_learning_plan(topic: str) -> str:
    """Create a milestone-based learning plan for a topic."""
    key = topic.lower().strip()

    if key in _MILESTONE_TEMPLATES:
        steps = _MILESTONE_TEMPLATES[key]
    else:
        steps = [{"step": s["step"].format(topic=topic.title()),
                  "level": s["level"]} for s in _GENERIC_MILESTONES]

    plan = {
        "id": str(uuid.uuid4())[:8],
        "topic": key,
        "created": datetime.now().isoformat(timespec="seconds"),
        "steps": [
            {**s, "done": False} for s in steps
        ],
    }

    # Replace existing plan for same topic, or append
    _data["milestones"] = [m for m in _data["milestones"] if m["topic"] != key]
    _data["milestones"].append(plan)
    learning_repo.save_plan(plan["id"], plan["topic"], plan["created"], plan["steps"])

    return _format_plan(plan)


def _format_plan(plan: dict[str, Any]) -> str:
    """Format a learning plan for display."""
    lines = [f"Learning Plan: {plan['topic'].title()}\n"]
    for i, step in enumerate(plan["steps"], 1):
        check = "x" if step["done"] else " "
        lines.append(f"  [{check}] {i}. [{step['level']}] {step['step']}")

    done = sum(1 for s in plan["steps"] if s["done"])
    total = len(plan["steps"])
    pct = int(done / total * 100) if total else 0
    bar_filled = int(pct / 10)
    bar = "█" * bar_filled + "░" * (10 - bar_filled)
    lines.append(f"\n  Progress: {bar} {pct}% ({done}/{total})")
    lines.append(f"\n  Say \"complete step {done + 1}\" to mark the next step done!")

    return "\n".join(lines)


def _show_all_plans() -> str:
    """Show all active learning plans."""
    plans = _data.get("milestones", [])
    if not plans:
        return "You don't have any learning plans yet. Say \"create a learning plan for Python\" to start!"

    lines = [f"Your Learning Plans ({len(plans)}):\n"]
    for plan in plans:
        done = sum(1 for s in plan["steps"] if s["done"])
        total = len(plan["steps"])
        pct = int(done / total * 100) if total else 0
        lines.append(f"  {plan['topic'].title():<16} {pct}% ({done}/{total} steps)")

    lines.append(f"\nSay \"show plan for [topic]\" for details.")
    return "\n".join(lines)


def _complete_step(topic: str, step_num: int) -> str:
    """Mark a step as done in a learning plan."""
    key = topic.lower().strip()
    plan = next((m for m in _data["milestones"] if m["topic"] == key), None)

    if not plan:
        return f"No learning plan found for {topic.title()}. Create one first!"

    if step_num < 1 or step_num > len(plan["steps"]):
        return f"Step {step_num} doesn't exist. The plan has {len(plan['steps'])} steps."

    step = plan["steps"][step_num - 1]
    if step["done"]:
        return f"Step {step_num} is already completed!"

    step["done"] = True
    learning_repo.update_plan_steps(key, plan["steps"])

    done = sum(1 for s in plan["steps"] if s["done"])
    total = len(plan["steps"])

    if done == total:
        return f"Step {step_num} completed! You've finished the entire {topic.title()} plan! Amazing work!"

    return f"Step {step_num} completed! ({done}/{total} done). Keep going!"


# ═══════════════════════════════════════════════════════════════════════════
#  5. INTENT DETECTION & ROUTING
# ═══════════════════════════════════════════════════════════════════════════

_LEARN_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bi want to learn\s+(.+)", re.IGNORECASE),
    re.compile(r"\bteach me\s+(.+)", re.IGNORECASE),
    re.compile(r"\bhelp me learn\s+(.+)", re.IGNORECASE),
]

_PRACTICE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bpractice\s+(.+)", re.IGNORECASE),
    re.compile(r"\bgive me\s+(?:some\s+)?practice\s+(?:tasks?|questions?)\s*(?:for\s+)?(.+)?", re.IGNORECASE),
    re.compile(r"\bpractice\s+tasks?\s+(?:for\s+)?(.+)", re.IGNORECASE),
]

_SUGGEST_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bwhat should i learn\b", re.IGNORECASE),
    re.compile(r"\bsuggest.+to learn\b", re.IGNORECASE),
    re.compile(r"\blearning suggestions?\b", re.IGNORECASE),
    re.compile(r"\brecommend.+to learn\b", re.IGNORECASE),
]

_INTEREST_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(show|my|view)\s+interests?\b", re.IGNORECASE),
    re.compile(r"\bwhat do i like\b", re.IGNORECASE),
]

_PLAN_CREATE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bcreate\s+(?:a\s+)?(?:learning\s+)?plan\s+(?:for\s+)?(.+)", re.IGNORECASE),
    re.compile(r"\blearning\s+plan\s+(?:for\s+)?(.+)", re.IGNORECASE),
    re.compile(r"\broadmap\s+(?:for\s+)?(.+)", re.IGNORECASE),
]

_PLAN_SHOW_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(?:show|view)\s+(?:my\s+)?(?:learning\s+)?plans?\b", re.IGNORECASE),
    re.compile(r"\bmy\s+progress\b", re.IGNORECASE),
    re.compile(r"\bshow\s+plan\s+(?:for\s+)?(.+)", re.IGNORECASE),
]

_COMPLETE_PATTERN = re.compile(
    r"\bcomplete\s+step\s+(\d+)\s*(?:(?:of|in|for)\s+(.+))?", re.IGNORECASE
)


def is_learning_command(user_input: str) -> bool:
    """Return True if the input is a learning-related command."""
    text = user_input.strip()
    all_patterns = (
        _LEARN_PATTERNS + _PRACTICE_PATTERNS + _SUGGEST_PATTERNS +
        _INTEREST_PATTERNS + _PLAN_CREATE_PATTERNS + _PLAN_SHOW_PATTERNS
    )
    if any(p.search(text) for p in all_patterns):
        return True
    if _COMPLETE_PATTERN.search(text):
        return True
    return False


def handle_learning_command(user_input: str, memory: Any) -> str:
    """Route a learning command to the right handler."""
    text = user_input.strip()

    # --- Complete step ---
    m = _COMPLETE_PATTERN.search(text)
    if m:
        step_num = int(m.group(1))
        topic = m.group(2)
        if not topic:
            # Use the last/only plan's topic
            plans = _data.get("milestones", [])
            if plans:
                topic = plans[-1]["topic"]
            else:
                return "No learning plan found. Create one first!"
        return _complete_step(topic.strip(), step_num)

    # --- Show interests ---
    if any(p.search(text) for p in _INTEREST_PATTERNS):
        return _format_interests()

    # --- Show plans / progress ---
    for p in _PLAN_SHOW_PATTERNS:
        m = p.search(text)
        if m:
            groups = m.groups()
            # "show plan for python" -> specific topic
            topic_match = groups[-1] if groups and groups[-1] else None
            if topic_match:
                key = topic_match.strip().lower()
                plan = next((p for p in _data["milestones"] if p["topic"] == key), None)
                if plan:
                    return _format_plan(plan)
                return f"No plan found for {topic_match.strip().title()}. Say \"create plan for {topic_match.strip()}\" to make one!"
            return _show_all_plans()

    # --- Create plan ---
    for p in _PLAN_CREATE_PATTERNS:
        m = p.search(text)
        if m:
            topic = m.group(1).strip().rstrip(".,!?")
            return _create_learning_plan(topic)

    # --- Learning suggestions ---
    if any(p.search(text) for p in _SUGGEST_PATTERNS):
        return _suggest_next_topics(memory)

    # --- Practice ---
    for p in _PRACTICE_PATTERNS:
        m = p.search(text)
        if m:
            topic = (m.group(1) or "").strip().rstrip(".,!?")
            if not topic:
                # Use top interest
                top = get_top_interests(1)
                topic = top[0][0] if top else "python"
            return _generate_practice(topic)

    # --- Learn topic ---
    for p in _LEARN_PATTERNS:
        m = p.search(text)
        if m:
            topic = m.group(1).strip().rstrip(".,!?")
            # Track the interest
            _data["interests"][topic.lower()] = _data["interests"].get(topic.lower(), 0) + 3
            _save_interests()

            lines = [
                f"Great choice! Let's start learning {topic.title()}.\n",
                "Here's what I can do for you:\n",
                f"  1. \"create plan for {topic}\"  -- step-by-step roadmap",
                f"  2. \"practice {topic}\"         -- hands-on tasks",
                f"  3. \"what should I learn next\" -- personalised suggestions",
                f"\nWhat would you like to try first?",
            ]
            return "\n".join(lines)

    return "I'm not sure what learning command you mean. Try: \"I want to learn Python\" or \"practice Python\""
