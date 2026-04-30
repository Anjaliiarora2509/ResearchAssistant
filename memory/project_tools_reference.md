---
name: Tools Reference
description: When to use each tool (web_search, fetch_url, save_finding), their parameters, the DISCOVER→DEEP READ→REMEMBER pattern, and prompt tuning notes.
type: project
---

## Three tools and their roles

| Tool | Phase | Trigger |
|---|---|---|
| `web_search` | DISCOVER | Current events, live data, recent developments |
| `fetch_url` | DEEP READ | After search returns a URL; snippet insufficient |
| `save_finding` | REMEMBER | After extracting a meaningful fact — always same response as retrieval |

## DISCOVER → DEEP READ → REMEMBER pattern

```
web_search()      ← find candidate sources
fetch_url()       ← extract full content (same LLM response as web_search when possible)
save_finding()    ← distill and store (same LLM response — never a separate turn)
```

`parallel_tool_calls=True` is set so the LLM can emit all three in one response.
`_handle_tool_round` in `research_loop.py` injects `save_finding` if the LLM forgets.

## Tool parameters

**web_search:** `query: str`
**fetch_url:** `url: str` — must start with `http://` or `https://`
**save_finding:** `key: str` (short label), `value: str` (distilled insight, never raw content)

## When NOT to use each tool

- `web_search` — stable facts, definitions, history, math
- `fetch_url` — without a concrete URL; never fabricate URLs
- `save_finding` — to store raw content; as a substitute for answering; duplicates

## Prompt tuning notes (model-specific)

- `llama-3.1-8b-instant` (current): needs verbose, explicit prompts with CAPS emphasis and negative examples ("Do NOT use for..."). Negative examples are load-bearing.
- Frontier models (GPT-4, Claude): intent-based, concise — over-specification hurts.
- Always re-tune `SYSTEM_PROMPT` and tool `description` fields when switching models.

## Citation rule (config.py SYSTEM_PROMPT)

Only cite URLs that appeared in a `web_search` or `fetch_url` tool result during the session. Never cite from training data. The LLM has hallucinated LinkedIn URLs in the past despite this instruction — small models may still do it occasionally.

**How to apply:** When the user asks about tool behaviour, prompt tuning, or citation issues — use this as the reference. The tool descriptions in `tools.py` schemas are the primary levers for changing LLM tool-selection behaviour.
