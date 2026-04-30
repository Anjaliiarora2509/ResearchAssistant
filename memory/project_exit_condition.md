---
name: Exit Condition & Loop Safety
description: Why the iteration cap exists, what happens without it, and the force-summary fallback — learned from a real infinite-loop trace on "Tell me everything about AI".
type: project
---

## The problem: while True without a cap

Without `range(5)`, the LLM can loop forever by repeatedly calling `save_finding` — each confirmation looks like progress but no new information is gained. Observed in a real trace: 9+ iterations, all `save_finding` from training data, zero `fetch_url` calls, no `stop`.

The LLM cannot self-terminate reliably. `finish_reason = "stop"` is controlled by the LLM — any architecture that relies solely on it is unsafe.

## The fix: range(5) + force_summary fallback

```python
for iteration in range(5):          # hard ceiling — Python enforces, not LLM
    response = call_llm(...)
    if finish_reason == "tool_calls":
        _handle_tool_round(...)
    else:
        return answer               # clean exit

_force_summary()                    # called only if all 5 iterations used tool_calls
```

`_force_summary` passes the full `messages[]` to the LLM with `tool_choice="none"` — so partial research is not lost, but no more tool calls are possible.

## Guarantees

| Guarantee | Mechanism |
|---|---|
| Always terminates | `range(5)` — Python, not LLM |
| Partial research preserved | Full `messages[]` passed to summary call |
| No tools in summary | `tool_choice="none"` |
| User always gets a response | Clean answer OR "Agent quit after 5 loops..." + summary |

## Key takeaway

> The exit condition is a correctness requirement, not an optimisation. The iteration cap is the only component guaranteed to terminate the loop regardless of LLM behaviour.

**How to apply:** If the user wants to change `_MAX_ITERATIONS`, understand that higher values allow more research but increase cost and risk of spinning. The current value is 5 in `research_loop.py`.
