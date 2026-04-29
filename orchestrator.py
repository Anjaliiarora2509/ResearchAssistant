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
        try:
            args = json.loads(arguments)
        except json.JSONDecodeError as exc:
            return f"Error: could not parse tool arguments — {exc}"

        dispatch = {
            "web_search": lambda: self.tools.web_search(args["query"]),
            "fetch_url": lambda: self.tools.fetch_url(args["url"]),
            "save_finding": lambda: self.tools.save_finding(args["key"], args["value"]),
        }

        handler = dispatch.get(name)
        if handler is None:
            return f"Error: unknown tool '{name}'."
        try:
            return handler()
        except KeyError as exc:
            return f"Error: missing required argument {exc} for tool '{name}'."
        except Exception as exc:  # noqa: BLE001
            return f"Error executing tool '{name}': {exc}"

    def run(self, topic: str) -> str:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": topic}
        ]
           
        while True:
          
            response = call_llm(self.client, messages)
            choice = response.choices[0]
            
            print(choice)
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
