"""
Creative Collaboration Layer for Aisha AI Assistant (Phase 7 Step 5).

Brainstorming support, alternative generation, assumption challenging,
perspective expansion, and ideation scaffolding.

Design principles:
    - NEVER flood the user with ideas
    - NEVER dominate creativity or force conclusions
    - Offer scaffolding, not solutions
    - Challenge assumptions gently ("What if..." not "You're wrong about...")
    - Support divergent thinking without overwhelming
    - Maximum 3-5 suggestions per request

Usage::

    from creative_collaboration import creative_collaboration

    result = creative_collaboration.brainstorm("AI assistant architecture")
    assumptions = creative_collaboration.challenge_assumptions(
        "Users always want fast responses"
    )
    perspectives = creative_collaboration.expand_perspective(
        "We need a database", dimensions=["technical", "user_experience"]
    )
"""

from __future__ import annotations

import os
import random
import re
import sys
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Assumption detection signals
_ASSUMPTION_SIGNALS = [
    (r"\balways\b", "always"),
    (r"\bnever\b", "never"),
    (r"\bmust\b", "must"),
    (r"\bonly way\b", "only way"),
    (r"\beveryone\b", "everyone"),
    (r"\bno one\b", "no one"),
    (r"\bobviously\b", "obviously"),
    (r"\bclearly\b", "clearly"),
    (r"\bimpossible\b", "impossible"),
    (r"\bcertain\b", "certain"),
    (r"\bneed to\b", "need to"),
    (r"\bhave to\b", "have to"),
    (r"\bshould\b", "should"),
    (r"\bcan't\b", "can't"),
    (r"\bwon't work\b", "won't work"),
]

# Perspective dimensions
_PERSPECTIVE_DIMENSIONS = {
    "technical": {
        "label": "Technical",
        "prompts": [
            "What technical constraints or opportunities does this create?",
            "What's the simplest technical approach that could work?",
            "Are there existing tools or patterns that address this?",
        ],
    },
    "user_experience": {
        "label": "User Experience",
        "prompts": [
            "How would someone actually use this day-to-day?",
            "What friction points might users encounter?",
            "What would make this feel intuitive?",
        ],
    },
    "business": {
        "label": "Business / Value",
        "prompts": [
            "What value does this create for people?",
            "What's the cost of doing this vs. not doing it?",
            "Who benefits most from this approach?",
        ],
    },
    "ethical": {
        "label": "Ethical",
        "prompts": [
            "Are there privacy or consent implications?",
            "Could this disadvantage any group of people?",
            "What would responsible implementation look like?",
        ],
    },
    "aesthetic": {
        "label": "Aesthetic / Feel",
        "prompts": [
            "How should this *feel* to interact with?",
            "What mood or tone does this create?",
            "What's the design language that fits here?",
        ],
    },
    "practical": {
        "label": "Practical",
        "prompts": [
            "What's the minimum viable version of this?",
            "What resources and timeline does this require?",
            "What could go wrong in practice?",
        ],
    },
}

# SCAMPER-inspired ideation framework
_SCAMPER_PROMPTS = {
    "substitute": "What could you replace or swap out?",
    "combine": "What could you merge or combine with something else?",
    "adapt": "How could you adapt an existing solution?",
    "modify": "What could you make bigger, smaller, or change the emphasis of?",
    "purpose": "Could this serve a different purpose than intended?",
    "eliminate": "What could you remove or simplify?",
    "rearrange": "What if you changed the order or structure?",
}

# Reframing templates
_REFRAME_TEMPLATES = [
    "What if instead of {problem}, you focused on {reframe}?",
    "Looking at this from a different angle: {reframe}",
    "What if the constraint was actually a feature? {reframe}",
    "Flipping the perspective: {reframe}",
]

# Random creative stimuli
_CREATIVE_STIMULI = [
    "What would this look like in 10 years?",
    "How would a child approach this problem?",
    "What's the opposite of what you're doing now?",
    "If you had unlimited resources, what would you do differently?",
    "What would the simplest possible version of this be?",
    "What would make someone *excited* about this?",
    "What would a complete beginner wonder about this?",
    "If this was a physical object, what would it look like?",
    "What's the story behind this idea?",
    "What would you do if you couldn't fail?",
]


# ---------------------------------------------------------------------------
# Creative Collaboration Engine
# ---------------------------------------------------------------------------

class CreativeCollaboration:
    """
    Brainstorming support that scaffolds creative thinking without
    dominating or flooding.

    No persistent state — operates as a stateless creative companion.
    """

    def __init__(self) -> None:
        print("  [CreativeCollaboration] Initialized")

    # ----- Brainstorming ---------------------------------------------------

    def brainstorm(
        self,
        topic: str,
        existing_ideas: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Generate brainstorming scaffolding for a topic.

        Returns structured prompts and frameworks, NOT finished ideas.
        """
        result: dict[str, Any] = {
            "topic": topic,
            "framework": [],
            "stimulus_questions": [],
            "next_steps": [],
        }

        # SCAMPER-inspired framework (pick 3-4 relevant prompts)
        scamper_items = list(_SCAMPER_PROMPTS.items())
        selected = random.sample(scamper_items, min(4, len(scamper_items)))
        for key, prompt in selected:
            result["framework"].append({
                "technique": key,
                "prompt": prompt,
            })

        # Creative stimulus questions
        stimuli = random.sample(
            _CREATIVE_STIMULI,
            min(3, len(_CREATIVE_STIMULI)),
        )
        result["stimulus_questions"] = stimuli

        # If existing ideas provided, suggest expansions
        if existing_ideas:
            result["expansions"] = []
            for idea in existing_ideas[:3]:
                result["expansions"].append({
                    "original": idea[:100],
                    "prompt": f"What if you took '{idea[:50]}...' further — what's the next evolution?",
                })

        # Suggest concrete next steps (invitational)
        result["next_steps"] = [
            f"Pick the most exciting angle on '{topic}' and spend 5 minutes exploring it",
            "Write down the first idea that feels *wrong* — it might unlock something",
            "What's the version of this idea you'd be most excited to build?",
        ]

        return result

    # ----- Assumption Challenging ------------------------------------------

    def challenge_assumptions(self, text: str) -> list[str]:
        """
        Identify implicit assumptions in the text and generate
        gentle challenges.

        Uses invitational language: "What if..." not "You're wrong about..."
        """
        challenges: list[str] = []
        lower = text.lower()

        for pattern, signal in _ASSUMPTION_SIGNALS:
            if re.search(pattern, lower):
                challenge = self._generate_challenge(signal, text)
                if challenge:
                    challenges.append(challenge)

        # If no explicit signals, offer a generic assumption check
        if not challenges:
            challenges.append(
                f"What's the core assumption behind this? "
                f"What would change if it wasn't true?"
            )

        return challenges[:4]  # Never overwhelm

    # ----- Perspective Expansion -------------------------------------------

    def expand_perspective(
        self,
        idea: str,
        dimensions: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Explore an idea from multiple perspective dimensions.

        If no dimensions specified, picks 3 relevant ones.
        """
        if dimensions:
            dims = [
                d for d in dimensions
                if d in _PERSPECTIVE_DIMENSIONS
            ]
        else:
            dims = random.sample(
                list(_PERSPECTIVE_DIMENSIONS.keys()),
                min(3, len(_PERSPECTIVE_DIMENSIONS)),
            )

        perspectives = []
        for dim in dims:
            defn = _PERSPECTIVE_DIMENSIONS[dim]
            prompt = random.choice(defn["prompts"])
            perspectives.append({
                "dimension": dim,
                "label": defn["label"],
                "prompt": prompt,
            })

        return {
            "idea": idea[:200],
            "perspectives": perspectives,
            "suggestion": "Consider exploring your idea through these different lenses.",
        }

    # ----- Alternative Generation ------------------------------------------

    def generate_alternatives(
        self, idea: str, count: int = 3,
    ) -> list[str]:
        """
        Suggest alternative approaches or framings for an idea.

        Returns invitational alternatives, not replacements.
        """
        count = min(count, 5)  # Cap to avoid flooding
        alternatives: list[str] = []

        # Variation strategies
        strategies = [
            ("simplify", f"A simpler version might be: what's the core of '{idea[:50]}...'?"),
            ("flip", f"What's the opposite approach to '{idea[:50]}...'?"),
            ("combine", f"What if you combined '{idea[:50]}...' with something unexpected?"),
            ("constrain", f"What if you had half the resources for '{idea[:50]}...'?"),
            ("expand", f"What's the ambitious, unconstrained version of '{idea[:50]}...'?"),
            ("analogize", f"Is there a completely different domain where '{idea[:50]}...' has been solved?"),
        ]

        selected = random.sample(strategies, min(count, len(strategies)))
        for _, alt in selected:
            alternatives.append(alt)

        return alternatives

    # ----- Reframing -------------------------------------------------------

    def reframe(self, problem_statement: str) -> list[str]:
        """
        Offer different framings of a problem statement.

        Returns 2-3 alternative ways to think about the problem.
        """
        reframes: list[str] = []

        # Generate reframing suggestions
        short = problem_statement[:60].rstrip(".")

        reframe_ideas = [
            f"the outcome you want rather than the obstacle you face",
            f"what's already working well and how to build on it",
            f"the smallest step that would make progress right now",
            f"who else has faced something similar and what they did",
            f"what would make this problem worth having",
        ]

        selected = random.sample(reframe_ideas, min(3, len(reframe_ideas)))
        for reframe_text in selected:
            template = random.choice(_REFRAME_TEMPLATES)
            reframes.append(template.format(
                problem=short,
                reframe=reframe_text,
            ))

        return reframes

    # ----- Random Stimulus -------------------------------------------------

    def random_stimulus(self, domain: str | None = None) -> str:
        """
        Return a creative prompt/stimulus to spark thinking.

        Domain-aware when specified.
        """
        stimuli = list(_CREATIVE_STIMULI)

        if domain and domain in _PERSPECTIVE_DIMENSIONS:
            # Add domain-specific prompts
            domain_prompts = _PERSPECTIVE_DIMENSIONS[domain]["prompts"]
            stimuli.extend(domain_prompts)

        return random.choice(stimuli)

    # ----- Ideation Scaffolding --------------------------------------------

    def get_ideation_scaffolding(self, topic: str) -> dict[str, Any]:
        """
        Provide a structured ideation framework for a topic.

        Combines multiple creative techniques into a coherent workflow.
        """
        return {
            "topic": topic,
            "phases": [
                {
                    "name": "Explore",
                    "description": "Understand the landscape",
                    "prompts": [
                        f"What do you already know about '{topic}'?",
                        f"What excites you most about '{topic}'?",
                        f"What's the biggest challenge with '{topic}'?",
                    ],
                },
                {
                    "name": "Diverge",
                    "description": "Generate many possibilities",
                    "prompts": random.sample(_CREATIVE_STIMULI, 3),
                },
                {
                    "name": "Challenge",
                    "description": "Question your assumptions",
                    "prompts": [
                        "What assumptions are you making?",
                        "What would a skeptic say about your best idea?",
                        "What's the opposite of your current approach?",
                    ],
                },
                {
                    "name": "Converge",
                    "description": "Select and refine",
                    "prompts": [
                        "Which idea feels most exciting?",
                        "Which idea would be easiest to try?",
                        "Which idea would create the most value?",
                    ],
                },
            ],
        }

    # ----- Diagnostics -----------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Return creative collaboration status."""
        return {
            "engine": "active",
            "capabilities": [
                "brainstorming", "assumption_challenging",
                "perspective_expansion", "alternative_generation",
                "reframing", "ideation_scaffolding",
            ],
            "perspective_dimensions": list(_PERSPECTIVE_DIMENSIONS.keys()),
            "scamper_techniques": list(_SCAMPER_PROMPTS.keys()),
        }

    # ----- Internal Helpers ------------------------------------------------

    @staticmethod
    def _generate_challenge(signal: str, text: str) -> str:
        """Generate a gentle assumption challenge for a detected signal."""
        challenges = {
            "always": "What if this isn't always the case? When might it not apply?",
            "never": "Are there edge cases where this might actually work?",
            "must": "Is this truly a requirement, or could there be flexibility here?",
            "only way": "What other approaches haven't been considered yet?",
            "everyone": "Is this universally true, or are there different perspectives?",
            "no one": "Has anyone tried this in a different context or domain?",
            "obviously": "What seems obvious can sometimes hide interesting nuances — what might you be overlooking?",
            "clearly": "What would someone who disagrees with this say?",
            "impossible": "What would need to change to make this possible?",
            "certain": "What's the evidence for this certainty? Where could uncertainty hide?",
            "need to": "Is this a need or a preference? What would happen without it?",
            "have to": "What if this wasn't a hard constraint? What opens up?",
            "should": "Who says so? What's the reasoning behind this expectation?",
            "can't": "What would 'can' look like, even partially?",
            "won't work": "What conditions would need to be true for this to work?",
        }
        return challenges.get(signal, "")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

creative_collaboration = CreativeCollaboration()
