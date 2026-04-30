"""
Tool definitions and handlers for the ResearchAssistant agent.

Each retrieval concern is its own class (SRP).  ToolRegistry composes them
and exposes the registry that Orchestrator uses for schema advertising and
dispatch.
"""

from __future__ import annotations

import logging
import os
import time
import urllib.parse
import urllib.request
import urllib.error
from dataclasses import dataclass
from functools import wraps
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
_MIN_CONTENT_CHARS: int = 500
_BLOCKED_DOMAINS: frozenset[str] = frozenset({
    "tech.yahoo.com", "news.google.com", "twitter.com",
    "linkedin.com", "facebook.com", "reddit.com",
})

# ---------------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------------

_RETRYABLE_HTTP_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})


def retry(max_attempts: int = 3, base_delay: float = 1.0) -> Callable:
    """Exponential backoff retry decorator.

    Retries on any exception whose HTTP status code (if present) is in
    _RETRYABLE_HTTP_CODES, or on non-HTTP exceptions (timeouts, DNS errors).
    Raises the final exception if all attempts are exhausted.
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            for attempt in range(max_attempts):
                try:
                    return fn(*args, **kwargs)
                except urllib.error.HTTPError as exc:
                    if exc.code not in _RETRYABLE_HTTP_CODES or attempt == max_attempts - 1:
                        raise
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        "retry: attempt=%d/%d HTTP %d — retrying in %.1fs",
                        attempt + 1, max_attempts, exc.code, delay,
                    )
                    time.sleep(delay)
                except Exception:
                    if attempt == max_attempts - 1:
                        raise
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        "retry: attempt=%d/%d — retrying in %.1fs",
                        attempt + 1, max_attempts, delay,
                    )
                    time.sleep(delay)
        return wrapper
    return decorator


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
    """Bundles an LLM-facing JSON schema with its Python handler."""

    schema: dict[str, Any]
    handler: Callable[..., str]

    @property
    def name(self) -> str:
        return self.schema["function"]["name"]


# ---------------------------------------------------------------------------
# WebSearchRetriever — owns Tavily client and web_search logic
# ---------------------------------------------------------------------------


class WebSearchRetriever:
    """Wraps the Tavily API and exposes a single web_search method.

    Raises:
        ValueError: If TAVILY_API_KEY is not set in the environment.
    """

    def __init__(self) -> None:
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            raise ValueError(
                "TAVILY_API_KEY is not set. "
                "Add it to your .env file before starting the assistant."
            )
        self._tavily = TavilyClient(api_key=api_key)

    def web_search(self, query: str, max_results: int = _WEB_SEARCH_DEFAULT_MAX_RESULTS) -> str:
        try:
            response = self._search_raw(query, max_results)
        except Exception as exc:
            logger.error("web_search: all retries exhausted — %s", exc)
            return f"Error: web search failed after retries — {exc}"
        results: list[dict[str, Any]] = response.get("results", [])
        results = [
            r for r in results
            if urllib.parse.urlparse(r["url"]).netloc.removeprefix("www.") not in _BLOCKED_DOMAINS
        ]
        if not results:
            return "No results found."
        return "\n\n".join(
            f"Title: {r['title']}\nURL: {r['url']}\nSummary: {r['content']}"
            for r in results
        )

    @retry(max_attempts=3, base_delay=1.0)
    def _search_raw(self, query: str, max_results: int) -> dict[str, Any]:
        return self._tavily.search(query=query, max_results=max_results)


# ---------------------------------------------------------------------------
# UrlFetcher — owns HTTP retrieval logic
# ---------------------------------------------------------------------------


class UrlFetcher:
    """Fetches and validates the text content of a URL."""

    def fetch_url(self, url: str) -> str:
        domain = urllib.parse.urlparse(url).netloc.removeprefix("www.")
        if domain in _BLOCKED_DOMAINS:
            logger.info("fetch_url: blocked domain=%s", domain)
            return f"Skipped: '{domain}' is a listing/aggregator page. Choose a direct article URL."

        try:
            text = self._fetch_raw(url)
        except urllib.error.HTTPError as exc:
            logger.warning("fetch_url: HTTP %d %s — %s", exc.code, exc.reason, url)
            return f"Error fetching URL (HTTP {exc.code}): {exc.reason}"
        except urllib.error.URLError as exc:
            logger.warning("fetch_url: URL error %s — %s", exc.reason, url)
            return f"Error fetching URL: {exc.reason}"
        except Exception as exc:  # noqa: BLE001
            logger.warning("fetch_url: unexpected error %s — %s", exc, url)
            return f"Unexpected error fetching URL: {exc}"

        if len(text) < _MIN_CONTENT_CHARS:
            logger.warning("fetch_url: thin content len=%d url=%s", len(text), url)
            return f"Page returned too little content ({len(text)} chars) — likely a login wall or error page."

        return text

    def _fetch_raw(self, url: str) -> str:
        """Decode, truncate, and return page text. Raises on network errors (for retry)."""
        logger.info("fetch_url: requesting %s", url)
        t0 = time.perf_counter()
        text = self._http_get(url)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        text = text.strip()
        truncated = len(text) > _FETCH_MAX_CHARS
        if truncated:
            text = text[:_FETCH_MAX_CHARS] + f"\n\n[truncated — {len(text)} chars total]"
        logger.info(
            "fetch_url: done fetch_ms=%.0f raw_chars=%d truncated=%s",
            elapsed_ms, len(text), truncated,
        )
        return text or "Page fetched successfully but contained no readable text."

    @retry(max_attempts=2, base_delay=0.5)
    def _http_get(self, url: str) -> str:
        """Perform the HTTP GET and return decoded text. Raises on any network error."""
        req = urllib.request.Request(url, headers={"User-Agent": "ResearchAssistant/1.0"})
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT_SECONDS) as resp:
            charset: str = resp.headers.get_content_charset("utf-8")
            return resp.read().decode(charset, errors="replace")


# ---------------------------------------------------------------------------
# FindingStore — owns working memory
# ---------------------------------------------------------------------------


class FindingStore:
    """Stores distilled insights in an in-memory key/value dict."""

    def __init__(self) -> None:
        self._findings: dict[str, str] = {}

    def save_finding(self, key: str, value: str) -> str:
        logger.info("save_finding: key=%s value_len=%d", key, len(value))
        self._findings[key] = value
        return f"Finding saved under '{key}'."


# ---------------------------------------------------------------------------
# ToolRegistry — composes the three retrievers and exposes the registry
# ---------------------------------------------------------------------------


class ToolRegistry:
    """Builds and owns the tool registry consumed by ToolDispatcher.

    Composes WebSearchRetriever, UrlFetcher, and FindingStore; owns no
    business logic of its own.
    """

    def __init__(self) -> None:
        self._searcher = WebSearchRetriever()
        self._fetcher = UrlFetcher()
        self._store = FindingStore()
        self.registry: dict[str, ToolEntry] = self._build_registry()

    @property
    def definitions(self) -> list[dict[str, Any]]:
        """Return all tool schemas suitable for passing to the LLM."""
        return [entry.schema for entry in self.registry.values()]

    def _build_registry(self) -> dict[str, ToolEntry]:
        entries = [
            ToolEntry(schema=_WEB_SEARCH_SCHEMA,  handler=self._searcher.web_search),
            ToolEntry(schema=_FETCH_URL_SCHEMA,    handler=self._fetcher.fetch_url),
            ToolEntry(schema=_SAVE_FINDING_SCHEMA, handler=self._store.save_finding),
        ]
        return {entry.name: entry for entry in entries}


# ---------------------------------------------------------------------------
# Tools — backward-compatible alias so existing callers need no changes
# ---------------------------------------------------------------------------

Tools = ToolRegistry
