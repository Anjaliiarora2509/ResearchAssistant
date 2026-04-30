"""
Tool definitions and handlers for the ResearchAssistant agent.

Each tool bundles its LLM-facing JSON schema with its Python handler via the
ToolEntry dataclass.  The Tools class owns all stateful resources (API clients,
working-memory store) and exposes a registry that the Orchestrator uses for
both schema advertising and dispatch.
"""

from __future__ import annotations

import logging
import os
import time
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)

from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_FETCH_TIMEOUT_SECONDS: int = 100
_FETCH_MAX_CHARS: int = 2_000
_WEB_SEARCH_DEFAULT_MAX_RESULTS: int = 2

# ---------------------------------------------------------------------------
# LLM tool schemas
# ---------------------------------------------------------------------------

_WEB_SEARCH_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "DISCOVER: Search the web ONLY for information that changes over time — "
            "breaking news, current prices, live scores, recent events, "
            "who currently holds a position, or anything that may have changed "
            "in the last year. Do NOT use for historical facts, definitions, "
            "geography, math, or stable knowledge."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to look up on the web.",
                }
            },
            "required": ["query"],
        },
    },
}

_FETCH_URL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "fetch_url",
        "description": (
            "DEEP READ: Retrieve the full text content of a specific URL for detailed analysis. "
            "Use this AFTER web_search has returned a URL, or when the user supplies a URL directly. "
            "Do NOT guess or fabricate URLs. "
            "Do NOT use when a web_search snippet already contains sufficient information."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": (
                        "The fully-qualified URL to fetch. "
                        "Must begin with http:// or https://."
                    ),
                }
            },
            "required": ["url"],
        },
    },
}

_SAVE_FINDING_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "save_finding",
        "description": (
            "REMEMBER: Store a distilled insight or key fact into working memory. "
            "Call this AFTER extracting meaningful information from web_search or fetch_url. "
            "Do NOT store raw or unprocessed content — summarize the fact first. "
            "Do NOT use this as a substitute for the final answer."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": (
                        "A short label identifying the finding, "
                        "e.g. 'btc_price' or 'article_date'."
                    ),
                },
                "value": {
                    "type": "string",
                    "description": (
                        "The distilled insight or fact to remember. "
                        "Must be a plain string — never an array or object. "
                        "If you have multiple URLs or items, join them with commas into one string."
                    ),
                },
            },
            "required": ["key", "value"],
        },
    },
}

# ---------------------------------------------------------------------------
# ToolEntry — pairs a schema with its handler
# ---------------------------------------------------------------------------


@dataclass
class ToolEntry:
    """Bundles an LLM-facing JSON schema with its Python handler.

    Attributes:
        schema:  The OpenAI-compatible function schema advertised to the LLM.
        handler: The callable invoked when the LLM requests this tool.
    """

    schema: dict[str, Any]
    handler: Callable[..., str]

    @property
    def name(self) -> str:
        """Return the tool name as declared in the schema."""
        return self.schema["function"]["name"]


# ---------------------------------------------------------------------------
# Tools — owns resources and registers all tool handlers
# ---------------------------------------------------------------------------


class Tools:
    """Stateful container for all agent tools.

    Initializes external API clients, maintains working memory, and exposes a
    registry that maps tool names to ToolEntry objects.

    Raises:
        ValueError: If a required environment variable (e.g. TAVILY_API_KEY)
                    is missing.
    """

    def __init__(self) -> None:
        self._tavily = self._init_tavily_client()
        self._findings: dict[str, str] = {}
        self.registry: dict[str, ToolEntry] = self._build_registry()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def definitions(self) -> list[dict[str, Any]]:
        """Return all tool schemas in a list suitable for passing to the LLM."""
        return [entry.schema for entry in self.registry.values()]

    # ------------------------------------------------------------------
    # Tool handlers
    # ------------------------------------------------------------------

    def web_search(self, query: str, max_results: int = _WEB_SEARCH_DEFAULT_MAX_RESULTS) -> str:
        """Search the web and return a formatted summary of results.

        Args:
            query:       The search query string.
            max_results: Maximum number of results to return (default 5).

        Returns:
            A newline-separated string of Title / URL / Summary blocks, or
            a plain message when no results are found.
        """
        response = self._tavily.search(query=query, max_results=max_results)
        results: list[dict[str, Any]] = response.get("results", [])
        if not results:
            return "No results found."
        return "\n\n".join(
            f"Title: {r['title']}\nURL: {r['url']}\nSummary: {r['content']}"
            for r in results
        )

    def fetch_url(self, url: str) -> str:
        """Retrieve and return the text content of a URL.

        Truncates the response to _FETCH_MAX_CHARS to stay within LLM context
        limits.  Returns a descriptive error string instead of raising so the
        LLM can react gracefully.  URL format is pre-validated by FetchUrlInput.

        Args:
            url: The fully-qualified URL to fetch (http/https, pre-validated).

        Returns:
            The decoded page text (possibly truncated), or an error string.
        """
        print(f"[fetch_url] Fetching {url} ...", flush=True)
        logger.info("fetch_url: requesting %s", url)
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ResearchAssistant/1.0"})
            with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT_SECONDS) as resp:
                charset: str = resp.headers.get_content_charset("utf-8")
                text: str = resp.read().decode(charset, errors="replace")
        except urllib.error.HTTPError as exc:
            print(f"[fetch_url] ERROR HTTP {exc.code} {exc.reason}", flush=True)
            logger.warning("fetch_url: HTTP %d %s — %s", exc.code, exc.reason, url)
            return f"Error fetching URL (HTTP {exc.code}): {exc.reason}"
        except urllib.error.URLError as exc:
            print(f"[fetch_url] ERROR {exc.reason}", flush=True)
            logger.warning("fetch_url: URL error %s — %s", exc.reason, url)
            return f"Error fetching URL: {exc.reason}"
        except Exception as exc:  # noqa: BLE001
            print(f"[fetch_url] ERROR {exc}", flush=True)
            logger.warning("fetch_url: unexpected error %s — %s", exc, url)
            return f"Unexpected error fetching URL: {exc}"

        elapsed_ms = (time.perf_counter() - t0) * 1000
        text = text.strip()
        truncated = len(text) > _FETCH_MAX_CHARS
        if truncated:
            text = text[:_FETCH_MAX_CHARS] + f"\n\n[truncated — {len(text)} chars total]"
        print(f"[fetch_url] Done — {len(text)} chars in {elapsed_ms:.0f}ms", flush=True)
        logger.info(
            "fetch_url: done fetch_ms=%.0f raw_chars=%d truncated=%s",
            elapsed_ms, len(text), truncated,
        )
        return text or "Page fetched successfully but contained no readable text."

    def save_finding(self, key: str, value: str) -> str:
        """Store a distilled insight in working memory under a short label.

        Overwrites any previous finding stored under the same key.  Input is
        pre-validated and normalised by SaveFindingInput before this is called.

        Args:
            key:   A short, non-empty label identifying the finding.
            value: The distilled insight to store (plain string, pre-validated).

        Returns:
            A confirmation string.
        """
        self._findings[key] = value
        return f"Finding saved under '{key}'."

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _init_tavily_client() -> TavilyClient:
        """Initialise and return a TavilyClient using the env-configured API key.

        Raises:
            ValueError: If TAVILY_API_KEY is not set in the environment.
        """
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            raise ValueError(
                "TAVILY_API_KEY is not set. "
                "Add it to your .env file before starting the assistant."
            )
        return TavilyClient(api_key=api_key)

    def _build_registry(self) -> dict[str, ToolEntry]:
        """Construct and return the tool registry."""
        entries = [
            ToolEntry(schema=_WEB_SEARCH_SCHEMA,   handler=self.web_search),
            ToolEntry(schema=_FETCH_URL_SCHEMA,     handler=self.fetch_url),
            ToolEntry(schema=_SAVE_FINDING_SCHEMA,  handler=self.save_finding),
        ]
        return {entry.name: entry for entry in entries}
