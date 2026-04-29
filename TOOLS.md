# Extended Toolset Reference

This document describes the three tools available in the Research Assistant and how they interact within the agentic loop. It extends the architecture described in [README.md](README.md).

---

## Tool Overview

| Tool | Role | Trigger phrase |
|---|---|---|
| `web_search` | **DISCOVER** — locate relevant sources | "find", "search", "what is", current events |
| `fetch_url` | **DEEP READ** — retrieve full content from a specific URL | "read", "summarize", "extract from" |
| `save_finding` | **REMEMBER** — store a key insight for use in the final answer | after extracting a meaningful fact |

Each tool serves a distinct phase of research. The LLM selects tools based on the `description` field in `TOOL_DEFINITIONS` — see the [README: Tool Definitions vs. tools.py](README.md#tool-definitions-vs-toolspy) section for how that selection works.

---

## Tool Descriptions

### `web_search` — DISCOVER

**Purpose:** Queries the web (via Tavily) to locate URLs and short summaries relevant to the user's question. Use this to find *where* information lives, not to extract full content.

**When the model should call it:**
- The question involves current events, live data, or recent developments
- The answer is not derivable from training data alone
- The model needs to identify candidate sources before reading further

**When NOT to call it:**
- For stable facts, definitions, or historical knowledge well within training data
- When a specific URL is already known — use `fetch_url` instead
- When a finding has already been saved — avoid redundant re-searching

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `query` | `string` | The search query. Should be specific and keyword-rich. |

**Example `TOOL_DEFINITIONS` entry:**

```json
{
  "type": "function",
  "function": {
    "name": "web_search",
    "description": "Search the web for current events, recent news, or time-sensitive information. Use this to DISCOVER relevant sources. Do NOT use for history, definitions, or stable facts.",
    "parameters": {
      "type": "object",
      "properties": {
        "query": {
          "type": "string",
          "description": "The search query"
        }
      },
      "required": ["query"]
    }
  }
}
```

**`tools.py` implementation stub:**

```python
def web_search(self, query: str) -> str:
    # Calls Tavily API; returns JSON string of results
    ...
```

---

### `fetch_url` — DEEP READ

**Purpose:** Retrieves the full text content of a specific URL. Use this after `web_search` has identified a promising source, or when the user provides a URL directly.

**When the model should call it:**
- A `web_search` result returned a URL likely to contain the needed detail
- The user explicitly references a URL or article
- A shallow snippet from search is insufficient — the model needs the full page

**When NOT to call it:**
- Without a concrete URL — never fabricate or guess URLs
- As a substitute for `web_search` when no URL is yet known
- On URLs that are likely to return binary files, login walls, or paywalled content

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `url` | `string` | The fully-qualified URL to fetch (must begin with `http://` or `https://`). |

**Example `TOOL_DEFINITIONS` entry:**

```json
{
  "type": "function",
  "function": {
    "name": "fetch_url",
    "description": "Retrieve the full text content of a specific URL for deep reading and analysis. Use this AFTER web_search has identified a relevant source, or when the user supplies a URL. Do NOT guess or fabricate URLs.",
    "parameters": {
      "type": "object",
      "properties": {
        "url": {
          "type": "string",
          "description": "The fully-qualified URL to fetch"
        }
      },
      "required": ["url"]
    }
  }
}
```

**`tools.py` implementation stub:**

```python
def fetch_url(self, url: str) -> str:
    # HTTP GET; returns extracted page text
    ...
```

---

### `save_finding` — REMEMBER

**Purpose:** Stores a key insight or extracted fact into the agent's working memory so it can be referenced when composing the final answer. This is a write-only accumulator — it does not retrieve or search.

**When the model should call it:**
- A meaningful fact has just been extracted from `web_search` or `fetch_url`
- The model wants to preserve a piece of evidence before the context shifts
- Multi-step research where intermediate conclusions need to be anchored

**When NOT to call it:**
- To store raw, unprocessed content — distill first, then save
- As a substitute for answering — findings must still be synthesized into a final response
- More than once for the same fact — avoid duplicates

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `key` | `string` | A short label identifying the finding (e.g., `"btc_price"`, `"article_date"`). |
| `value` | `string` | The distilled insight or fact to store. |

**Example `TOOL_DEFINITIONS` entry:**

```json
{
  "type": "function",
  "function": {
    "name": "save_finding",
    "description": "Store a key insight or extracted fact into working memory. Use this AFTER distilling meaningful information from web_search or fetch_url results. Do NOT use to store raw content or as a substitute for the final answer.",
    "parameters": {
      "type": "object",
      "properties": {
        "key": {
          "type": "string",
          "description": "A short label for the finding"
        },
        "value": {
          "type": "string",
          "description": "The distilled insight or fact to remember"
        }
      },
      "required": ["key", "value"]
    }
  }
}
```

**`tools.py` implementation stub:**

```python
def save_finding(self, key: str, value: str) -> str:
    # Writes to an internal dict; returns confirmation string
    ...
```

---

## Workflow: How the Tools Interact

The three tools map to a natural research flow that the LLM drives autonomously inside the agentic loop:

```
User Question
      │
      ▼
 web_search()          ← DISCOVER: find candidate sources
      │
      │  (returns URLs + snippets)
      ▼
 fetch_url()           ← DEEP READ: extract full content from best URL
      │
      │  (returns page text)
      ▼
 save_finding()        ← REMEMBER: distill and store the key fact
      │
      │  (loop may repeat for additional sub-questions)
      ▼
 finish_reason = "stop"
      │
      ▼
 Final Answer          ← LLM synthesizes all saved findings
```

This is the **DISCOVER → DEEP READ → REMEMBER** pattern. The orchestrator does not enforce this order — the LLM decides the sequence based on `description` fields and the `SYSTEM_PROMPT`. The pattern emerges from well-written tool descriptions.

---

## Registering the Tools in the Orchestrator

Follow the three-step process from [README: Adding a New Tool](README.md#adding-a-new-tool):

1. **[tools.py](tools.py)** — add `fetch_url` and `save_finding` as methods on the `Tools` class below the existing `web_search` method.

2. **[config.py](config.py)** — append entries for `fetch_url` and `save_finding` to `TOOL_DEFINITIONS`. Use the JSON schemas shown above verbatim.

3. **[orchestrator.py](orchestrator.py)** — add dispatch branches in `_execute()`:

```python
elif tool_name == "fetch_url":
    return self.tools.fetch_url(**args)

elif tool_name == "save_finding":
    return self.tools.save_finding(**args)
```

`arguments` arrives as a JSON string. It is already parsed via `json.loads()` at [orchestrator.py:14](orchestrator.py#L14) before reaching `_execute()` — pass `**args` directly.

---

## Parallel vs. Sequential Considerations

With `parallel_tool_calls=False` (current default in [llm.py](llm.py)), the agent runs one tool per loop iteration. This is the correct default for this toolset because:

- `fetch_url` typically depends on a URL returned by `web_search`
- `save_finding` depends on content returned by `fetch_url`

If you switch to `parallel_tool_calls=True`, ensure the `SYSTEM_PROMPT` and tool descriptions account for the fact that the model may issue multiple tool calls in a single turn before seeing any results.

---

## Prompt Tuning Notes

The same tuning guidance from [README: Prompt Tuning by Model](README.md#prompt-tuning-by-model) applies to these tools. For smaller models (`llama-3.1-8b-instant`), the `description` fields must be explicit about both when TO use and when NOT TO use each tool. The negative examples (`Do NOT use for...`) are load-bearing — removing them causes the model to over-call tools.
