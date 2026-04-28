from groq_call import make_groq_call


class TopicSearcher:
    """A class responsible for searching a user-provided topic with Groq."""

    def __init__(self, client, model=None):
        self.client = client
        self.model = model 

    def search_topic(self, topic, system_prompt=None):
        if not topic:
            raise ValueError("Topic cannot be empty. Please provide a question or topic to search for.")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": f"Research and summarize the following topic: {topic}"})

        return make_groq_call(self.client, messages, self.model)
