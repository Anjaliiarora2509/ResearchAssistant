import os
from groq import Groq
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configuration
LLM_MODEL = "llama-3.3-70b-versatile"

def get_groq_client():
    """
    Initialize and return the Groq client using the API key from environment variables.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not found in environment variables. Please check your .env file.")
    return Groq(api_key=api_key)

def make_groq_call(client, messages, model=None, max_tokens=None):
    if model is None:
        model = LLM_MODEL
    kwargs = {"model": model, "messages": messages}
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return client.chat.completions.create(**kwargs)

