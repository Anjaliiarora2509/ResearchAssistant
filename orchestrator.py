import json
import logging
import time
import uuid
from pydantic import ValidationError
from groq_client import get_groq_client
from llm import call_llm
from tools import Tools
from config import SYSTEM_PROMPT
from schemas import WebSearchInput, FetchUrlInput, SaveFindingInput

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_TOOL_RESULT_MAX_CHARS = 1_200

_SCHEMA_MAP = {
    "web_search":   WebSearchInput,
    "fetch_url":    FetchUrlInput,
    "save_finding": SaveFindingInput,
}


class Orchestrator:
    def __init__(self):
        self.client = get_groq_client()
        self.tools = Tools()

    def _execute(self, name: str, arguments: str, trace_id: str) -> str:
        try:
            args = json.loads(arguments)
        except json.JSONDecodeError as exc:
            return f"Error: could not parse tool arguments — {exc}"

        schema = _SCHEMA_MAP.get(name)
        if schema:
            try:
                args = schema(**args).model_dump()
            except ValidationError as exc:
                return f"Invalid arguments for '{name}': {exc}"

        entry = self.tools.registry.get(name)
        if entry is None:
            return f"Error: unknown tool '{name}'."

        logger.info("[%s] tool=%s args=%s", trace_id, name, arguments)
        t0 = time.perf_counter()
        try:
            result = entry.handler(**args)
        except Exception as exc:  # noqa: BLE001
            result = f"Error executing tool '{name}': {exc}"
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info("[%s] tool=%s result_len=%d tool_ms=%.0f", trace_id, name, len(result), elapsed_ms)

        return result

    def run(self, topic: str) -> str:
        trace_id = uuid.uuid4().hex[:8]
        logger.info("[%s] START topic=%r", trace_id, topic)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": topic}
        ]

        for iteration in range(5):
            t0 = time.perf_counter()
            response = call_llm(self.client, messages)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            choice = response.choices[0]

            logger.info(
                "[%s] iter=%d finish=%s llm_ms=%.0f",
                trace_id, iteration, choice.finish_reason, elapsed_ms,
            )

            if choice.finish_reason == "tool_calls":
                assistant_message = choice.message
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
                            }
                        }
                        for tc in assistant_message.tool_calls
                    ]
                })
                for tc in assistant_message.tool_calls:
                    result = self._execute(tc.function.name, tc.function.arguments, trace_id)
                    if len(result) > _TOOL_RESULT_MAX_CHARS:
                        result = result[:_TOOL_RESULT_MAX_CHARS] + f"\n[truncated — {len(result)} chars total]"
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })
            else:
                final = choice.message.content
                logger.info("[%s] END iterations=%d", trace_id, iteration + 1)
                return final

        # Loop exhausted
        logger.warning("[%s] EXHAUSTED max iterations reached, requesting summary", trace_id)
        messages.append({
            "role": "user",
            "content": (
                "You have reached the maximum number of research steps. "
                "Summarize everything you have found so far into a final answer. "
                "Do not call any more tools."
            )
        })
        summary_response = call_llm(self.client, messages, tool_choice="none")
        summary = summary_response.choices[0].message.content
        logger.info("[%s] END summary_len=%d", trace_id, len(summary))
        return "Agent quit after 5 loops. Below is the result:\n\n" + summary
