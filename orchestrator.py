import json
from groq_client import get_groq_client
from llm import call_llm
from tools import Tools
from config import SYSTEM_PROMPT


class Orchestrator:
    def __init__(self):
        self.client = get_groq_client()
        self.tools = Tools()

    def _execute(self, name: str, arguments: str) -> str:
        args = json.loads(arguments)
        if name == "web_search":
            return self.tools.web_search(args["query"])
        raise ValueError(f"Unknown tool: {name}")

    def run(self, topic: str) -> str:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": topic}
        ]

        while True:
            response = call_llm(self.client, messages)
            choice = response.choices[0]

            if choice.finish_reason == "tool_calls":
                assistant_message = choice.message
                messages.append({
                    "role": "assistant",
                    "content": assistant_message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in assistant_message.tool_calls
                    ]
                })
                for tc in assistant_message.tool_calls:
                    result = self._execute(tc.function.name, tc.function.arguments)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result
                    })
            else:
                return choice.message.content
