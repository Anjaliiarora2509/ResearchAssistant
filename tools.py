import os
from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()


class Tools:
    def __init__(self):
        tavily_key = os.getenv("TAVILY_API_KEY")
        if not tavily_key:
            raise ValueError("TAVILY_API_KEY not found in .env file.")
        self.tavily = TavilyClient(api_key=tavily_key)

    def web_search(self, query: str, max_results: int = 5) -> str:
        response = self.tavily.search(query=query, max_results=max_results)
        results = response.get("results", [])
        if not results:
            return "No results found."
        return "\n\n".join(
            f"Title: {r['title']}\nURL: {r['url']}\nSummary: {r['content']}"
            for r in results
        )

    # --- Add new tool functions below this line ---
