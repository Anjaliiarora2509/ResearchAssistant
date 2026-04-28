from groq_call import get_groq_client
from TopicResearch import TopicSearcher


SYSTEM_PROMPT = "You must respond in exactly 2 short sentences. No more, no less. Do not add any extra explanation or details."


class Orchestrator:
    def __init__(self):
        self.client = get_groq_client()
        self.searcher = TopicSearcher(self.client)

    def run(self, topic):
        response = self.searcher.search_topic(topic, system_prompt=SYSTEM_PROMPT)
        return response.choices[0].message.content
