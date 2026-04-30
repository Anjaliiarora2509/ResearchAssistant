---
name: Backend Architecture
description: Full backend structure of ResearchAssistant — files, layers, agentic loop mechanics, tool_choice, and how to add a new tool.
type: project
---

## File map

| File | Class/Role |
|---|---|
| `groq_client.py` | Initialises Groq SDK client from `GROQ_API_KEY` |
| `config.py` | `LLM_MODEL`, `PLAN_LLM_MODEL`, `SYSTEM_PROMPT` |
| `llm.py` | Wraps `client.chat.completions.create()`; owns `_TOOL_DEFINITIONS` |
| `tools.py` | `WebSearchRetriever`, `UrlFetcher`, `FindingStore`, `ToolRegistry` |
| `schemas.py` | Pydantic input validation for all three tools |
| `tool_dispatcher.py` | `ToolDispatcher` — validates args, executes handler, truncates result |
| `planner.py` | `Planner` — one LLM call to decompose topic into 3 sub-questions |
| `research_loop.py` | `ResearchLoop` — iterative LLM ↔ tool loop, max 5 iterations |
| `orchestrator.py` | `Orchestrator` — wires all classes; exposes `run(topic) → str` |
| `main.py` | CLI entry point |
| `api.py` | FastAPI entry point |

## Agentic loop (research_loop.py)

```
for iteration in range(5):
    call LLM
    if finish_reason == "tool_calls":
        _handle_tool_round()   ← executes all tool calls, appends results
    else:
        return answer          ← clean exit

_force_summary()               ← called only if all 5 iterations used tool calls
```

- Each iteration = one LLM call. Tool calls consume the iteration.
- `parallel_tool_calls=True` — LLM can emit multiple tool calls per response.
- `_handle_tool_round` injects `save_finding` automatically if LLM retrieves but forgets to save.

## tool_choice values

| Value | Behaviour |
|---|---|
| `"auto"` | Model decides — biases toward tool use |
| `"none"` | Tools disabled — used for forced summary on exhaustion |

## Tools (tools.py)

| Class | Responsibility |
|---|---|
| `WebSearchRetriever` | Tavily API, `web_search()`, retry 3× with 1s backoff |
| `UrlFetcher` | HTTP GET, `fetch_url()`, retry 2× with 0.5s backoff |
| `FindingStore` | In-memory dict, `save_finding()` |
| `ToolRegistry` | Composes the three above, exposes `definitions` and `registry` |

Blocked domains (filtered from both `web_search` results and `fetch_url`):
`tech.yahoo.com`, `news.google.com`, `twitter.com`, `linkedin.com`, `facebook.com`, `reddit.com`

## Adding a new tool

1. Add a new class (e.g. `CalculatorTool`) in `tools.py` with its handler method.
2. Add its JSON schema constant in `tools.py`.
3. Register it in `ToolRegistry._build_registry()`.
4. Add a Pydantic schema in `schemas.py`.
5. Add it to `_SCHEMA_MAP` in `tool_dispatcher.py`.
No other files need to change.

**How to apply:** When the user asks about adding tools, modifying the loop, or changing retry behaviour — refer to this map. The seam for any UI/API integration is `Orchestrator.run(topic: str) → str`.
