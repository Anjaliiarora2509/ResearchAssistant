import os
import urllib.request
import urllib.error
from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()

_FETCH_TIMEOUT_SECONDS = 100
_FETCH_MAX_CHARS = 8000


class Tools:
    def __init__(self):
        tavily_key = os.getenv("TAVILY_API_KEY")
        if not tavily_key:
            raise ValueError("TAVILY_API_KEY not found in .env file.")
        self.tavily = TavilyClient(api_key=tavily_key)
        self._findings: dict[str, str] = {}

    def web_search(self, query: str, max_results: int = 5) -> str:
        response = self.tavily.search(query=query, max_results=max_results)
        results = response.get("results", [])
        if not results:
            return "No results found."
        return "\n\n".join(
            f"Title: {r['title']}\nURL: {r['url']}\nSummary: {r['content']}"
            for r in results
        )

    # --- Add new tool functions below this line ---

    def fetch_url(self, url: str) -> str:
        """DEEP READ: retrieve and return the text content of a URL.

        Truncates to _FETCH_MAX_CHARS to stay within context limits.
        Returns an error string (never raises) so the LLM can react gracefully.
        """
        if not url.startswith(("http://", "https://")):
            return f"Error: URL must begin with http:// or https://. Got: {url!r}"
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "ResearchAssistant/1.0"},
            )
            with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT_SECONDS) as resp:
                raw = resp.read()
                charset = resp.headers.get_content_charset("utf-8")
                text = raw.decode(charset, errors="replace")
        except urllib.error.HTTPError as exc:
            return f"Error fetching URL (HTTP {exc.code}): {exc.reason}"
        except urllib.error.URLError as exc:
            return f"Error fetching URL: {exc.reason}"
        except Exception as exc:  # noqa: BLE001
            return f"Unexpected error fetching URL: {exc}"

        text = text.strip()
        if len(text) > _FETCH_MAX_CHARS:
            text = text[:_FETCH_MAX_CHARS] + f"\n\n[truncated — {len(text)} chars total]"
        return text or "Page fetched successfully but contained no readable text."

    def save_finding(self, key: str, value) -> str:
        """REMEMBER: store a distilled insight under a short label.

        Overwrites any previous finding stored under the same key.
        Returns a confirmation string the LLM can use to verify the save.
        """
        key = key.strip()
        if not key:
            return "Error: key must be a non-empty string."
        # Coerce lists/dicts the LLM occasionally passes instead of a plain string
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        elif not isinstance(value, str):
            value = str(value)
        self._findings[key] = value
        return f"Finding saved under '{key}'."
