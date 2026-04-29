# Research Assistant

An agentic research assistant that uses a Groq-hosted LLM and real-time web search to answer questions about current events and time-sensitive topics.

---

## Architecture

```
User Input
    │
    ▼
┌─────────────────────────────────────────────────────┐
│                    Orchestrator                     │
│  (the only bridge between LLM world and tool world) │
│                                                     │
│   messages[] ──► call_llm() ──► Groq API (HTTP)     │
│       ▲                              │              │
│       │            finish_reason?    │              │
│       │           "tool_calls" ◄─────┘              │
│       │                │                            │
│       │           _execute()                        │
│       │                │                            │
│       └── tool result  ▼                            │
│                   Tools.web_search()                │
│                   (Tavily API, HTTP)                 │
└─────────────────────────────────────────────────────┘
    │
    ▼  finish_reason = "stop"
  Final Answer
```

**The LLM and your code live in separate worlds — HTTP only, no direct access.**

| Layer | File | Purpose |
|---|---|---|
| Client | [groq_client.py](groq_client.py) | Initializes the Groq SDK client from `GROQ_API_KEY` |
| Config | [config.py](config.py) | `LLM_MODEL`, `SYSTEM_PROMPT`, `TOOL_DEFINITIONS` |
| LLM caller | [llm.py](llm.py) | Wraps `client.chat.completions.create()` |
| Tools | [tools.py](tools.py) | Runnable tool implementations (Python code) |
| Orchestrator | [orchestrator.py](orchestrator.py) | Agentic loop — routes between LLM and tools |

---

## Tool Definitions vs. tools.py

These are two separate things that serve two different audiences:

| | `TOOL_DEFINITIONS` in [config.py](config.py) | [tools.py](tools.py) |
|---|---|---|
| **Read by** | The LLM | Your Python code |
| **Purpose** | Tells the model *when* and *how* to call a tool | Actually executes the tool |
| **Format** | JSON schema | Python class methods |

`TOOL_DEFINITIONS` has two critical fields:

- **`description`** — controls *when* the model picks a tool. A bad description leads to wrong tool selection or hallucinated arguments. The current `web_search` description explicitly states what NOT to use it for (history, definitions, stable facts) — this is intentional.
- **`parameters`** — controls *what arguments* the model generates. The schema must match exactly what `tools.py` expects.

---

## The Agentic Loop

`Orchestrator.run()` in [orchestrator.py](orchestrator.py) drives a `while True` loop with two exit conditions:

```
while True:
    response = call_llm(...)

    if finish_reason == "tool_calls":
        # 1. Append the assistant message FIRST (order matters)
        # 2. Execute each tool call
        # 3. Append each tool result linked by tool_call_id
        # → loop again

    else:  # finish_reason == "stop"
        return response content
```

Three invariants to respect:

1. **`finish_reason = "tool_calls"`** → model wants a tool, keep looping. **`finish_reason = "stop"`** → model is done, return the answer.
2. **`tool_call_id`** is the linking pin between a request and its result. Every tool result message must carry the `tool_call_id` from the corresponding tool call.
3. **The assistant message must be appended before the tool result** — the message list order is part of the protocol. Appending out of order causes an API error.

`arguments` arrives as a **JSON string**, not a dict. Always `json.loads()` it before passing to tool functions (see [orchestrator.py:14](orchestrator.py#L14)).

---

## tool_choice

[llm.py](llm.py) sets `tool_choice="auto"`.

| Value | Behavior |
|---|---|
| `"auto"` | Model decides whether to call a tool — but biases *toward* tool use, it is not neutral |
| `"none"` | Disables tools entirely; model must answer from training data |
| `{"type": "function", "function": {"name": "..."}}` | Forces a specific tool call |

There is no built-in "smart" mode. The model's judgment about when to search comes entirely from the `description` field in `TOOL_DEFINITIONS` and the `SYSTEM_PROMPT`.

---

## Parallel vs. Sequential Tool Calls

`parallel_tool_calls=False` is set in [llm.py](llm.py), so this agent runs tools **sequentially** — one tool per loop iteration, each result informing the next decision.

| Mode | When to use |
|---|---|
| Sequential (`parallel_tool_calls=False`) | Each tool result may change what the next query should be |
| Parallel | Multiple independent lookups where results don't depend on each other |

---

## Prompt Tuning by Model

The current model is `llama-3.1-8b-instant` (a smaller open model). **The same prompt does not work across all models** — always re-tune when switching.

| Model type | Prompt style |
|---|---|
| Smaller models (Llama 3) | Verbose, explicit, use CAPS for emphasis, add negative examples, reframe as positives |
| Frontier models (GPT-4) | Concise, intent-based, trust the model's judgment |
| Claude | Intent-based, XML tags, reasons before acting, naturally conservative with tools |

If you switch from `llama-3.1-8b-instant` to a frontier model, revisit `SYSTEM_PROMPT` and the `description` fields in `TOOL_DEFINITIONS` — what works for Llama will be over-specified for Claude or GPT-4.

---

## Setup

**Requirements:** Python 3.10+

```bash
pip install groq tavily-python python-dotenv
```

Create a `.env` file:

```
GROQ_API_KEY=your_groq_key
TAVILY_API_KEY=your_tavily_key
```

**Run:**

```python
from orchestrator import Orchestrator

agent = Orchestrator()
answer = agent.run("What is the current price of Bitcoin?")
print(answer)
```

---

## Adding a New Tool

1. Add a method to `Tools` in [tools.py](tools.py) below the marked line.
2. Add a new entry to `TOOL_DEFINITIONS` in [config.py](config.py) — include both when TO use it and when NOT TO use it in the description.
3. Add a dispatch branch in `Orchestrator._execute()` in [orchestrator.py](orchestrator.py#L13).

The orchestrator handles the rest automatically.
