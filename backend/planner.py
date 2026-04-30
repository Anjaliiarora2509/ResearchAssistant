"""Decomposes a research topic into focused sub-questions before the loop starts."""

import json
import logging
from groq import Groq
from .llm import call_llm
from .config import PLAN_LLM_MODEL

logger = logging.getLogger(__name__)

_PLANNER_SYSTEM_PROMPT = (
    "You are a research planner. Given a topic, return ONLY a JSON array "
    "of exactly 3 focused sub-questions. No explanation, no markdown. "
    'Example: ["What is X?", "How does X work?", "What are X\'s real-world uses?"]'
)


class Planner:
    """Breaks a broad topic into 3 focused sub-questions via a single LLM call.

    Responsible for:
    - Running one planning LLM call with no tools attached
    - Parsing and validating the returned JSON array
    - Falling back to the raw topic when the LLM response is unparseable
    """

    def __init__(self, client: Groq) -> None:
        self._client = client

    def decompose(self, topic: str, trace_id: str) -> list[str]:
        """Return a list of focused sub-questions for the given topic.

        Args:
            topic:     The user's original research question.
            trace_id:  Session trace ID used for log correlation.

        Returns:
            A list of sub-question strings. Falls back to ``[topic]`` if the
            LLM response cannot be parsed as a non-empty JSON array.
        """
        logger.info("[%s] PLAN starting decomposition", trace_id)
        planning_messages = [
            {"role": "system", "content": _PLANNER_SYSTEM_PROMPT},
            {"role": "user",   "content": topic},
        ]
        try:
            response = call_llm(self._client, planning_messages, tool_choice="none", model=PLAN_LLM_MODEL)
            sub_questions = json.loads(response.choices[0].message.content)
            if not isinstance(sub_questions, list) or not sub_questions:
                raise ValueError("planner returned empty or non-list response")
            logger.info("[%s] PLAN sub_questions=%s", trace_id, sub_questions)
            return sub_questions
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("[%s] PLAN fallback — %s", trace_id, exc)
            return [topic]
