from groq import Groq
from groq.types.chat import ChatCompletion
from config import LLM_MODEL, TOOL_DEFINITIONS


def call_llm(client: Groq, messages: list) -> ChatCompletion:
    return client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        tools=TOOL_DEFINITIONS,
        tool_choice="auto",
        parallel_tool_calls=False
    )
