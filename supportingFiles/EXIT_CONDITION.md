# Why the Agentic Loop Needs an Exit Condition

This document uses a real execution trace from the question `"Tell me everything about AI"` to explain why `while True` without a hard exit condition is dangerous, and what actually happens at runtime when no guard exists.

---

## The Execution Trace (Annotated)

Below is the exact sequence of LLM decisions recorded during the run, with commentary on what each one reveals.

---

### Iteration 1 — `web_search("AI")`

```
tool_calls → web_search(query="AI")
```

**What happened:** The model issued the broadest possible query — a single word. This is the model's first attempt to satisfy `"Tell me everything about AI"`. It searched, got results, and instead of fetching a URL or answering, it moved to saving findings directly from the snippet.

**Problem visible here:** The model did not plan. It jumped straight into tool use with no outline of what sub-topics to cover.

---

### Iterations 2, 3, 4 — Three consecutive `save_finding` calls, no search in between

```
tool_calls → save_finding("ai-definition",  "The ability of machines to learn...")
tool_calls → save_finding("ai-subfields",   "Machine learning, which involves...")
tool_calls → save_finding("ai-agents",      "An autonomous AI program...")
```

**What happened:** The model saved three facts derived from training data — not from the search results. It did not call `fetch_url` at all. It wrote findings from what it already knew, not from what it discovered.

**Problem visible here:** The model is using `save_finding` as a notepad for training-data recall, not as a REMEMBER step after DISCOVER and DEEP READ. Each `save_finding` call consumes one loop iteration without advancing the actual research.

---

### Iteration 5 — `web_search("AI history")`

```
tool_calls → web_search(query="AI history")
```

**What happened:** After saving three facts from memory, the model finally searched a second sub-topic. This is 5 iterations in and only the second `web_search` call.

**Problem visible here:** The model is burning iterations on `save_finding` calls that produce no new information. Real research budget (iterations) is being consumed by memory recall.

---

### Iterations 6, 7, 8, 9 — Four more `save_finding` calls

```
tool_calls → save_finding("ai-history-1940s-1950s",        "Alan Turing proposed...")
tool_calls → save_finding("ai-winter-expert-systems-...",   "In the late 1990s...")
tool_calls → save_finding("ai-generative-2000s",            "Generative AI is a type...")
tool_calls → save_finding("ai-rise-breakthroughs-2010",     "AI became mainstream...")
```

**What happened:** Four more findings saved in a row — again all from training data, not from the `web_search("AI history")` result. The model is in a `save_finding` loop, methodically offloading its training knowledge into the findings store.

**Problem visible here:** This is the infinite loop pattern. The model has found a repeatable action (`save_finding`) that always succeeds, always returns a confirmation, and never triggers `finish_reason = "stop"`. It will keep doing this indefinitely.

---

## Why `while True` Makes This Catastrophic

Without an exit condition the loop above runs like this:

```
Iteration  1  → web_search("AI")
Iteration  2  → save_finding(...)
Iteration  3  → save_finding(...)
Iteration  4  → save_finding(...)
Iteration  5  → web_search("AI history")
Iteration  6  → save_finding(...)
Iteration  7  → save_finding(...)
Iteration  8  → save_finding(...)
Iteration  9  → save_finding(...)
Iteration 10  → web_search("AI applications")      ← model discovers a new sub-topic
Iteration 11  → save_finding(...)
Iteration 12  → save_finding(...)
...
Iteration N   → still going
```

Each `save_finding` confirmation (`"Finding saved under 'key'."`) looks identical to a successful research step. The LLM has no way to distinguish "I am making progress" from "I am spinning in place." The orchestrator has no way to distinguish either — it just sees `finish_reason = "tool_calls"` and keeps looping.

**There is only one exit in `while True`:**

```python
# orchestrator.py
while True:
    response = call_llm(...)
    if finish_reason == "tool_calls":
        ...              # loop continues — no other way out
    else:                # finish_reason == "stop"
        return content   # only exit
```

If the LLM never emits `"stop"`, this function never returns. The process runs until the API rate limit is hit, the token budget is exhausted, or the process is killed manually.

---

## The Three Compounding Problems in This Trace

| # | Problem | Evidence in trace |
|---|---|---|
| 1 | Model uses `save_finding` to dump training data, not research results | Findings saved before any `fetch_url` was called |
| 2 | Each `save_finding` consumes a loop iteration with no new information gained | 4 consecutive saves after a single search |
| 3 | No iteration cap exists to force a stop | Loop continued past 9 iterations with no end in sight |

Any one of these alone is manageable. All three together create a loop that is both infinite and produces low-quality output — it never fetches real content, it never synthesises, and it never stops.

---

## Why the Output Was Bad Even If It Had Stopped

Even if the model had stopped at iteration 9 and composed a final answer, the answer would have been poor because:

- **No `fetch_url` was ever called** — all findings came from training data, not live sources
- **The single `web_search("AI")` result was never read** — it was used only to trigger saving from memory
- **All findings were shallow one-liners** — no depth, no citations, no current information

The exit condition problem and the output quality problem are linked. More iterations without a plan do not produce better output — they produce more shallow findings from memory.

---

## The Fix Applied in This Project

```python
# orchestrator.py — replaces while True
for _ in range(5):
    response = call_llm(self.client, messages)
    choice = response.choices[0]

    if choice.finish_reason == "tool_calls":
        ...  # execute tools, append results
    else:
        return choice.message.content  # clean exit

# Fallback: loop exhausted — force a summary from what was gathered
messages.append({
    "role": "user",
    "content": (
        "You have reached the maximum number of research steps. "
        "Summarize everything you have found so far into a final answer. "
        "Do not call any more tools."
    )
})
summary_response = call_llm(self.client, messages, tool_choice="none")
return (
    "Agent quit after 5 loops. Below is the result:\n\n"
    + summary_response.choices[0].message.content
)
```

**What this guarantees:**

| Guarantee | How |
|---|---|
| Loop always terminates | `range(5)` is a hard ceiling — Python enforces it, not the LLM |
| Partial research is not lost | Fallback call passes full `messages[]` to the LLM for summarisation |
| LLM cannot call more tools in the fallback | `tool_choice="none"` disables tool use on the summary call |
| User always gets a response | Either a clean answer or `"Agent quit after 5 loops..."` + summary |

---

## Key Takeaway

> The exit condition is not an optimisation — it is a correctness requirement.
>
> `finish_reason = "stop"` is controlled entirely by the LLM. Any architecture that relies solely on the LLM choosing to stop is not safe. The iteration cap in the orchestrator is the only component in this system that is guaranteed to terminate the loop regardless of LLM behaviour.
