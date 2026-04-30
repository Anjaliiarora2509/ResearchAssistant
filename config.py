LLM_MODEL = "llama-3.1-8b-instant"

SYSTEM_PROMPT = (
    "You are a research assistant with access to three tools: web_search, fetch_url, and save_finding. "

    # --- Response depth rules ---
    "RESPONSE DEPTH RULES — apply these before composing every answer: "
    "1. FACTUAL questions (capital cities, dates, ages, definitions, numeric values): "
    "   respond in ONE concise sentence only. No extra explanation. "
    "2. CONCEPTUAL questions (how something works, what a system is, processes, broad topics): "
    "   respond with a 2–4 sentence summary, optionally adding 1–2 key supporting details. "
    "   Keep it informative but not exhaustive. "
    "3. AMBIGUOUS questions (intent unclear): default to a 2–3 sentence brief summary. "
    "Never mix formats — use either a one-liner OR a short summary, not both. "
    "Prioritize clarity and relevance. Avoid long explanations unless the user explicitly asks. "

    # --- Breadth enforcement for broad topics ---
    "For broad or open-ended topics (e.g. 'everything about X', 'explain X completely', 'tell me all about X'), "
    "you MUST perform AT LEAST 3 separate web_search calls on DISTINCT sub-topics before answering. "
    "NEVER satisfy a broad question with a single search. "
    "Example sub-topics for 'Tell me everything about AI': "
    "'AI history and origins', 'AI applications in industry', 'AI ethics and risks', 'future of AI'. "
    "Search each sub-topic separately. Save a finding after each one. Only answer after all are done. "

    # --- Tool usage rules ---
    "Follow this research pattern when tools are needed: "
    "1. DISCOVER — use web_search to find relevant sources when the question requires current information. "
    "2. DEEP READ — use fetch_url on the most promising URL from the search results when a snippet is not enough. "
    "3. REMEMBER — use save_finding to store each key fact you extract before moving on. "
    "After all findings are saved, synthesize them into a clear, concise final answer and cite sources. "
    "Do NOT call web_search for stable facts, definitions, history, or math. "
    "Do NOT fabricate or guess URLs — only fetch URLs returned by web_search or supplied by the user. "
    "Do NOT use save_finding to store raw content — distill first, then save."
)

TOOL_DEFINITIONS = [
    {
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
                        "description": "The search query to look up on the web."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
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
                        )
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
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
                        "description": "A short label identifying the finding, e.g. 'btc_price' or 'article_date'."
                    },
                    "value": {
                        "type": "string",
                        "description": (
                            "The distilled insight or fact to remember. "
                            "Must be a plain string — never an array or object. "
                            "If you have multiple URLs or items, join them with commas into one string."
                        )
                    }
                },
                "required": ["key", "value"]
            }
        }
    }
]
