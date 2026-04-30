"""Runs the iterative LLM ↔ tool research loop for a scoped topic."""

import logging
import time
from groq import Groq
from llm import call_llm
from tool_dispatcher import ToolDispatcher
from config import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

_MAX_ITERATIONS = 5
_LOOP_EXHAUSTED_PROMPT = (
    "You have reached the maximum number of research steps. "
    "Summarize everything you have found so far into a final answer. "
    "Do not call any more tools."
)


class ResearchLoop:
    """Drives the iterative LLM ↔ tool loop for a scoped research topic.

    Responsible for:
    - Building and maintaining the message history
    - Calling the LLM on each iteration and reading finish_reason
    - Handing tool-call rounds off to ToolDispatcher
    - Requesting a forced summary when the iteration budget is exhausted
    """

    def __init__(self, client: Groq, dispatcher: ToolDispatcher) -> None:
        self._client = client
        self._dispatcher = dispatcher

    def run(self, scoped_topic: str, trace_id: str) -> str:
        """Execute the research loop and return the final answer string.

        Args:
            scoped_topic:  The user question or planner-scoped sub-question list.
            trace_id:      Session trace ID used for log correlation.

        Returns:
            The LLM's final answer, or a forced summary if iterations are exhausted.
        """
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": scoped_topic},
        ]

        for iteration in range(_MAX_ITERATIONS):
            t0 = time.perf_counter()
            response = call_llm(self._client, messages)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            choice = response.choices[0]

            logger.info(
                "[%s] iter=%d finish=%s llm_ms=%.0f",
                trace_id, iteration, choice.finish_reason, elapsed_ms,
            )

            if choice.finish_reason == "tool_calls":
                messages = self._handle_tool_round(messages, choice.message, trace_id)
            else:
                logger.info("[%s] END iterations=%d", trace_id, iteration + 1)
                return choice.message.content

        return self._force_summary(messages, trace_id)

    def _handle_tool_round(self, messages: list, assistant_message, trace_id: str) -> list:
        """Append the assistant turn and all tool results to the message history."""
        messages.append({
            "role": "assistant",
            "content": assistant_message.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in assistant_message.tool_calls
            ],
        })
        for tc in assistant_message.tool_calls:
            result = self._dispatcher.execute(tc.function.name, tc.function.arguments, trace_id)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })
        return messages

    def _force_summary(self, messages: list, trace_id: str) -> str:
        """Request a plain-text summary after the iteration budget is exhausted."""
        logger.warning("[%s] EXHAUSTED max iterations reached, requesting summary", trace_id)
        messages.append({"role": "user", "content": _LOOP_EXHAUSTED_PROMPT})
        summary_response = call_llm(self._client, messages, tool_choice="none")
        summary = summary_response.choices[0].message.content
        logger.info("[%s] END summary_len=%d", trace_id, len(summary))
        return "Agent quit after 5 loops. Below is the result:\n\n" + summary
