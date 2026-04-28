# Building a Research Assistant with Groq and Llama

This project walks through building a clean, modular AI research assistant using the Groq API and the Llama 3.3 model. By the end, you will have a working tool that takes any topic as input and returns a concise, controlled summary.

---

## Project Structure

```
ResearchAssistant/
├── groq_call.py       # Groq client setup and API wrapper
├── TopicResearch.py   # TopicSearcher — pure search utility
├── orchestrator.py    # Orchestrator — controls behavior and prompt
└── main.py            # Entry point
```

Each file has a single responsibility. This is intentional — and one of the core lessons of this project.

---

## The Code

### 1. `groq_call.py` — API Foundation

```python
def get_groq_client():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not found in environment variables.")
    return Groq(api_key=api_key)

def make_groq_call(client, messages, model=None, max_tokens=None):
    if model is None:
        model = LLM_MODEL
    kwargs = {"model": model, "messages": messages}
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return client.chat.completions.create(**kwargs)
```

> **Key lesson: `max_tokens` is the only hard enforcement for response length.**
> The API accepts an optional `max_tokens` argument. When set, the model physically cannot generate more tokens than the limit — regardless of what the prompt says. This is different from the system prompt, which is just a suggestion.

---

### 2. `TopicResearch.py` — Pure Search Utility

```python
class TopicSearcher:
    def __init__(self, client, model=None):
        self.client = client
        self.model = model

    def search_topic(self, topic, system_prompt=None):
        if not topic:
            raise ValueError("Topic cannot be empty.")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": f"Research and summarize the following topic: {topic}"})

        return make_groq_call(self.client, messages, self.model)
```

> **Key lesson: Keep utility classes free of hardcoded behavior.**
> `TopicSearcher` does not decide *how* the model should respond — it only handles *what* to send. The system prompt is accepted as a parameter, not hardcoded inside. This makes the class reusable across different contexts with different tones or constraints.

---

### 3. `orchestrator.py` — The Brain

```python
SYSTEM_PROMPT = "You must respond in exactly 2 short sentences. No more, no less. Do not add any extra explanation or details."

class Orchestrator:
    def __init__(self):
        self.client = get_groq_client()
        self.searcher = TopicSearcher(self.client)

    def run(self, topic):
        response = self.searcher.search_topic(topic, system_prompt=SYSTEM_PROMPT)
        return response.choices[0].message.content
```

> **Key lesson: The orchestrator owns the behavior, not the utility.**
> The system prompt lives here — in the class that decides *how* the assistant should behave. If you want to change the tone, response style, or constraints, you change it in one place. The `TopicSearcher` below it stays untouched.

---

### 4. `main.py` — Entry Point

```python
def main():
    try:
        orchestrator = Orchestrator()
        topic = input("Enter a question or topic to search: ").strip()
        if not topic:
            raise ValueError("No topic entered.")
        result = orchestrator.run(topic)
        print("Response from Groq:")
        print(result)
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
```

> **Key lesson: `main` should only wire things together.**
> No business logic, no API calls, no prompt construction — just user input, orchestrator call, and output. Keeping `main` thin means you can swap the orchestrator or add a UI later without rewriting anything.

---

## Key Lessons

### How the Chat API roles work

Every message sent to the API has a `role`:

| Role | Purpose |
|------|---------|
| `system` | Sets the model's behavior and tone before the conversation starts |
| `user` | The actual question or input from the human |
| `assistant` | The model's previous replies (used for multi-turn conversations) |

The model reads them in order — `system` first to understand its role, then `user` to know what to respond to.

---

### System prompt vs `max_tokens`

> **System prompts influence behavior. `max_tokens` enforces it.**

| Control | Type | Reliability |
|---------|------|-------------|
| `"Respond in 2 lines"` in system prompt | Suggestion | Low — model may ignore it |
| `"You must respond in exactly 2 sentences..."` | Stronger suggestion | Medium — better wording helps |
| `max_tokens=80` | Hard API cap | High — model cannot exceed it |

When you need strict output length, always combine a clear system prompt with `max_tokens`.

---

### Separation of concerns

The project evolved through a deliberate refactoring:

1. Started with everything in one file (`groq_call.py`)
2. Moved `TopicSearcher` to its own file (`TopicResearch.py`)
3. Added an `Orchestrator` to wire components together
4. Moved the system prompt out of `TopicSearcher` into `Orchestrator`
5. Kept `main.py` as a thin entry point

Each step made the code easier to change without breaking other parts.

---

## Running the Project

Install dependencies:
```bash
pip install groq python-dotenv
```

Create a `.env` file:
```
GROQ_API_KEY=your_api_key_here
```

Run:
```bash
python main.py
```
