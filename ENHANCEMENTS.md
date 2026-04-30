# Architecture Enhancement Roadmap

Based on the current design documented in TOOLS.md and README.md — a sequential, single-agent loop with three tools (`web_search`, `fetch_url`, `save_finding`) driven by `llama-3.1-8b-instant` via Groq.

---

## Priority Matrix

| # | Enhancement | Impact | Effort | Type |
|---|---|---|---|---|
| 1 | Pydantic Input Validation | High | Low | Quick Win |
| 2 | Structured Logging & Trace ID | High | Low | Quick Win |
| 3 | Planning Phase (Topic Decomposition) | High | Medium | Quick Win |
| 4 | Tool Registry Pattern | Medium | Low | Quick Win |
| 5 | Retry with Exponential Backoff | High | Medium | Mid-term |
| 6 | Findings Persistence Layer | Medium | Medium | Mid-term |
| 7 | URL Quality Filter | Medium | Medium | Mid-term |
| 8 | Streaming Final Answer | Low | High | Long-term |

---

## Enhancement 1 — Pydantic Input Validation

**Problem it solves:**
The LLM occasionally generates malformed tool arguments — the real crash in this project was `save_finding` receiving an array instead of a string. The error was caught by the Groq API after the network call, not in Python. The current manual coercion in `tools.py` only covers `save_finding` and is fragile.

**Proposed solution:**
Define a Pydantic `BaseModel` for each tool's input in `config.py` or a new `schemas.py`. Validate inside `_execute()` before calling any tool:

```python
# schemas.py
from pydantic import BaseModel, field_validator

class WebSearchInput(BaseModel):
    query: str

class FetchUrlInput(BaseModel):
    url: str

    @field_validator("url")
    def must_be_http(cls, v):
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must begin with http:// or https://")
        return v

class SaveFindingInput(BaseModel):
    key: str
    value: str

    @field_validator("key")
    def key_not_empty(cls, v):
        if not v.strip():
            raise ValueError("key must not be empty")
        return v.strip()

    @field_validator("value", mode="before")
    def coerce_to_string(cls, v):
        if isinstance(v, list):
            return ", ".join(str(i) for i in v)
        return str(v)
```

```python
# orchestrator.py _execute()
SCHEMA_MAP = {
    "web_search":   WebSearchInput,
    "fetch_url":    FetchUrlInput,
    "save_finding": SaveFindingInput,
}
schema = SCHEMA_MAP.get(name)
if schema:
    try:
        validated = schema(**args)
        args = validated.model_dump()
    except ValidationError as exc:
        return f"Invalid arguments for '{name}': {exc}"
```

**Expected impact:**
- Eliminates API-level crashes from malformed LLM output
- Centralises all input rules in one place — adding a new tool means adding one schema class
- Validation errors are returned as tool result strings, keeping the loop alive

**Complexity:** Low

---

## Enhancement 2 — Structured Logging & Trace ID

**Problem it solves:**
The current `print(choice)` statements in `orchestrator.py` dump raw Groq response objects to stdout. There is no way to correlate a run's tool calls, measure per-tool latency, or replay a specific session for debugging.

**Proposed solution:**
Replace `print` statements with Python's `logging` module. Assign a `trace_id` (UUID) per `run()` call and include it in every log entry:

```python
import logging
import uuid
import time

logger = logging.getLogger(__name__)

def run(self, topic: str) -> str:
    trace_id = str(uuid.uuid4())[:8]
    logger.info(f"[{trace_id}] START topic={topic!r}")

    for iteration in range(5):
        t0 = time.perf_counter()
        response = call_llm(self.client, messages)
        elapsed = time.perf_counter() - t0
        logger.info(f"[{trace_id}] iter={iteration} finish={choice.finish_reason} llm_ms={elapsed*1000:.0f}")

        if choice.finish_reason == "tool_calls":
            for tc in assistant_message.tool_calls:
                logger.info(f"[{trace_id}] tool={tc.function.name} args={tc.function.arguments}")
                result = self._execute(tc.function.name, tc.function.arguments)
                logger.info(f"[{trace_id}] tool={tc.function.name} result_len={len(result)}")
```

**Expected impact:**
- Every run is fully traceable from a single `trace_id`
- LLM latency is measurable per iteration — immediately surfaces slow Groq calls
- Zero change to existing functionality — purely additive

**Complexity:** Low

---

## Enhancement 3 — Planning Phase (Topic Decomposition)

**Problem it solves:**
For broad questions like `"Tell me everything about AI"`, the LLM decomposes the topic ad hoc inside the research loop, producing inconsistent sub-topics and wasting iterations on redundant searches. The loop has no concept of a research plan — it reacts turn by turn.

**Proposed solution:**
Add a `_plan()` method that runs a single focused LLM call before the research loop. It returns a fixed list of sub-questions that the loop then works through:

```python
def _plan(self, topic: str) -> list[str]:
    planning_messages = [
        {"role": "system", "content": (
            "You are a research planner. Given a topic, return ONLY a JSON array "
            "of exactly 3 focused sub-questions. No explanation, no markdown. "
            'Example: ["What is X?", "How does X work?", "What are X real-world uses?"]'
        )},
        {"role": "user", "content": topic}
    ]
    response = call_llm(self.client, planning_messages, tool_choice="none")
    try:
        return json.loads(response.choices[0].message.content)
    except (json.JSONDecodeError, ValueError):
        return [topic]  # fallback: treat the full topic as one question

def run(self, topic: str) -> str:
    sub_questions = self._plan(topic)
    scoped_topic = (
        f"Research these specific sub-questions and answer each one:\n"
        + "\n".join(f"{i+1}. {q}" for i, q in enumerate(sub_questions))
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": scoped_topic}
    ]
    ...
```

**Expected impact:**
- Decomposition happens once, deterministically, before the loop starts
- The loop follows a fixed plan — cannot discover new sub-topics from search result terminology
- Directly addresses the infinite loop root cause for broad questions
- One extra LLM call upfront; saves multiple wasted iterations in the loop

**Complexity:** Medium

---

## Enhancement 4 — Tool Registry Pattern

**Problem it solves:**
Every new tool requires changes in three files: `tools.py` (implementation), `config.py` (schema), and `orchestrator.py` (dispatch branch). The dispatch dict in `_execute()` must be manually kept in sync with `TOOL_DEFINITIONS` in `config.py`. Adding a tool is a three-file operation with no enforcement that all three stay consistent.

**Proposed solution:**
Centralise tool registration so each tool is defined in one place:

```python
# tools.py
from dataclasses import dataclass
from typing import Callable

@dataclass
class ToolEntry:
    definition: dict       # the TOOL_DEFINITIONS JSON schema entry
    handler: Callable      # the Python function to call

class Tools:
    def __init__(self):
        ...
        self.registry: dict[str, ToolEntry] = {
            "web_search":   ToolEntry(WEB_SEARCH_DEFINITION,   self.web_search),
            "fetch_url":    ToolEntry(FETCH_URL_DEFINITION,     self.fetch_url),
            "save_finding": ToolEntry(SAVE_FINDING_DEFINITION,  self.save_finding),
        }

    @property
    def definitions(self) -> list[dict]:
        return [entry.definition for entry in self.registry.values()]
```

```python
# config.py — TOOL_DEFINITIONS replaced by:
from tools import Tools
TOOL_DEFINITIONS = Tools().definitions   # single source of truth

# orchestrator.py _execute() — dispatch replaced by:
entry = self.tools.registry.get(name)
if entry is None:
    return f"Error: unknown tool '{name}'."
return entry.handler(**args)
```

**Expected impact:**
- Adding a new tool is a one-file change in `tools.py` only
- `TOOL_DEFINITIONS` is always in sync with available handlers — impossible to have a tool defined but not dispatched, or dispatched but not defined
- Makes the system genuinely extensible without architectural changes

**Complexity:** Low

---

## Enhancement 5 — Retry with Exponential Backoff

**Problem it solves:**
Both `web_search` (Tavily API) and `fetch_url` (HTTP GET) make external network calls with no retry logic. A transient failure — rate limit, timeout, DNS blip — returns an error string immediately. The LLM then tries a different URL rather than retrying the failed one, burning an iteration and potentially missing the best source.

**Proposed solution:**
Wrap external calls with a retry decorator:

```python
import time
from functools import wraps

def retry(max_attempts: int = 3, base_delay: float = 1.0):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:
                    if attempt == max_attempts - 1:
                        raise
                    time.sleep(base_delay * (2 ** attempt))
        return wrapper
    return decorator

class Tools:
    @retry(max_attempts=3, base_delay=1.0)
    def web_search(self, query: str, max_results: int = 5) -> str:
        ...

    @retry(max_attempts=2, base_delay=0.5)
    def _fetch_raw(self, url: str) -> str:
        ...  # urllib call extracted here
```

**Expected impact:**
- Transient network failures are recovered transparently without consuming a loop iteration
- Reduces the "Error fetching URL (HTTP 503)" → wasted iteration → new URL search pattern
- `fetch_url` still returns a clean error string if all retries fail — loop continues safely

**Complexity:** Medium

---

## Enhancement 6 — Findings Persistence Layer

**Problem it solves:**
`self._findings` is an in-memory dict that is destroyed when `Orchestrator.run()` returns. Every session starts from zero — there is no way to resume a partial research session, share findings across questions, or audit what was saved over time.

**Proposed solution:**
Replace the in-memory dict with a thin persistence layer behind the same interface:

```python
import json
from pathlib import Path

class FindingsStore:
    def __init__(self, path: str = "findings.json"):
        self._path = Path(path)
        self._data: dict[str, str] = {}
        if self._path.exists():
            self._data = json.loads(self._path.read_text())

    def save(self, key: str, value: str) -> str:
        self._data[key] = value
        self._path.write_text(json.dumps(self._data, indent=2))
        return f"Finding saved under '{key}'."

    def all(self) -> dict[str, str]:
        return dict(self._data)
```

```python
# tools.py
class Tools:
    def __init__(self):
        ...
        self._store = FindingsStore()

    def save_finding(self, key: str, value: str) -> str:
        ...
        return self._store.save(key, value)
```

**Expected impact:**
- Research sessions survive process restarts
- Findings from previous runs can seed new sessions — avoids re-searching known facts
- `FindingsStore` is swappable (SQLite, Redis) without touching `Tools` or `Orchestrator`

**Complexity:** Medium

---

## Enhancement 7 — URL Quality Filter

**Problem it solves:**
`fetch_url` is called on any URL the LLM picks from search results — including news aggregator listing pages (Yahoo Tech, Google News), paywalled articles, and social media profiles. These return navigation menus, ad text, and login prompts rather than actual content, wasting an iteration and producing noise findings. This was directly observed in the execution traces.

**Proposed solution:**
Add a blocklist check and a content-quality check before returning from `fetch_url`:

```python
_BLOCKED_DOMAINS = {
    "tech.yahoo.com", "news.google.com", "twitter.com",
    "linkedin.com", "facebook.com", "reddit.com"
}

_MIN_CONTENT_CHARS = 500  # pages shorter than this are likely error/login pages

def fetch_url(self, url: str) -> str:
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.lstrip("www.")
    if domain in _BLOCKED_DOMAINS:
        return f"Skipped: '{domain}' is a listing/aggregator page. Choose a direct article URL."

    text = self._fetch_raw(url)

    if len(text) < _MIN_CONTENT_CHARS:
        return f"Page returned too little content ({len(text)} chars) — likely a login wall or error page."

    return text
```

**Expected impact:**
- Eliminates the listing-page fetch pattern that produced the poor AI summary in the observed trace
- The LLM receives a clear skip reason and picks a better URL on the next iteration
- Blocklist is a plain set — trivially extensible

**Complexity:** Medium

---

## Enhancement 8 — Streaming Final Answer

**Problem it solves:**
For long research sessions (5 iterations, multiple saves), the user sees nothing until the very end. The entire `run()` call is synchronous — the user waits with no feedback, no indication the agent is working, and no partial results.

**Proposed solution:**
Use Groq's streaming API on the final answer call only. Tool-call iterations remain synchronous (streaming partial tool calls is complex and not supported cleanly):

```python
def run(self, topic: str) -> str:
    ...
    for _ in range(5):
        response = call_llm(self.client, messages)
        if choice.finish_reason != "tool_calls":
            # Final answer — stream it
            return self._stream_answer(messages)
        ...

def _stream_answer(self, messages: list) -> str:
    stream = self.client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        stream=True,
        tool_choice="none"
    )
    chunks = []
    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        print(delta, end="", flush=True)
        chunks.append(delta)
    print()
    return "".join(chunks)
```

**Expected impact:**
- User sees the final answer appear word by word — significantly better perceived responsiveness
- No change to tool-call iterations — only the final synthesis is streamed
- Requires a small refactor of `call_llm` to support `stream=True`

**Complexity:** High

---

## Recommended Implementation Order

### Quick Wins (do first — low effort, high return)

1. **Enhancement 4 — Tool Registry** — eliminates the three-file sync problem before more tools are added
2. **Enhancement 1 — Pydantic Validation** — one-time fix that prevents the array crash class permanently
3. **Enhancement 2 — Structured Logging** — purely additive, makes all future debugging faster

### Mid-term (do next — medium effort, addresses root causes)

4. **Enhancement 3 — Planning Phase** — directly solves the broad-question loop quality problem
5. **Enhancement 7 — URL Quality Filter** — directly fixes the listing-page fetch pattern from the traces
6. **Enhancement 5 — Retry with Backoff** — makes network calls reliable without changing the loop logic

### Long-term (do when stable)

7. **Enhancement 6 — Findings Persistence** — valuable once the system is used across multiple sessions
8. **Enhancement 8 — Streaming** — UX improvement, not a correctness fix; address last
