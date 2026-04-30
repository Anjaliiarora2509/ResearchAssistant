"""Validates and dispatches LLM tool-call requests to their handlers."""

import json
import logging
import time
from pydantic import ValidationError
from tools import Tools
from schemas import WebSearchInput, FetchUrlInput, SaveFindingInput

logger = logging.getLogger(__name__)

_TOOL_RESULT_MAX_CHARS = 1_200

_SCHEMA_MAP = {
    "web_search":   WebSearchInput,
    "fetch_url":    FetchUrlInput,
    "save_finding": SaveFindingInput,
}


class ToolDispatcher:
    """Parses, validates, and executes a single tool call by name.

    Responsible for:
    - JSON-decoding the raw arguments string from the LLM
    - Running Pydantic validation against the tool's input schema
    - Invoking the handler and timing its execution
    - Truncating oversized results before they re-enter the message history
    """

    def __init__(self, tools: Tools) -> None:
        self._tools = tools

    def execute(self, name: str, arguments: str, trace_id: str) -> str:
        """Validate and run a tool call, returning a plain string result.

        Args:
            name:       The tool name as declared in the LLM schema.
            arguments:  Raw JSON string of arguments from the LLM.
            trace_id:   Session trace ID used for log correlation.

        Returns:
            The tool's output string, truncated to _TOOL_RESULT_MAX_CHARS,
            or a descriptive error string if anything goes wrong.
        """
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

        entry = self._tools.registry.get(name)
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

        if len(result) > _TOOL_RESULT_MAX_CHARS:
            result = result[:_TOOL_RESULT_MAX_CHARS] + f"\n[truncated — {len(result)} chars total]"
        return result
