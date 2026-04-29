LLM_MODEL = "llama-3.1-8b-instant"

SYSTEM_PROMPT = (
    "You are a research assistant with access to real-time web search. "
    "When answering a question, use the web_search tool when you need current information. "
    "After retrieving results, provide a clear and concise summary. "
    "Cite sources where relevant."
)

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web ONLY for information that changes over time — "
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
    }
]
