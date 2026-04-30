from groq import Groq
from groq.types.chat import ChatCompletion
from config import LLM_MODEL
from tools import ToolRegistry

_TOOL_DEFINITIONS = ToolRegistry().definitions


def call_llm(
    client: Groq,
    messages: list,
    tool_choice: str = "auto",
    model: str = LLM_MODEL,
) -> ChatCompletion:
    return client.chat.completions.create(
        model=model,
        messages=messages,
        tools=_TOOL_DEFINITIONS,
        tool_choice=tool_choice,
        parallel_tool_calls=False
    )
