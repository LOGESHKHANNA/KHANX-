import httpx
from typing import Any, Dict
from urllib.parse import quote
from app.agent.tools.base import BaseTool

class WikipediaTool(BaseTool):
    """Tool for fetching concise Wikipedia summaries for general knowledge queries."""
    name = "wikipedia_search"
    description = "Search Wikipedia for encyclopedic information, historical figures, science, concepts, and biographies."
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Topic or person to search on Wikipedia, e.g. 'Alan Turing' or 'Quantum Computing'."
            }
        },
        "required": ["query"]
    }

    async def execute(self, query: str, **kwargs: Any) -> str:
        """Execute Wikipedia REST API search."""
        try:
            search_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={quote(query)}&limit=1&namespace=0&format=json"

            headers = {
                "User-Agent": "KHANX-AiChatbot/1.0 (contact@khanx.ai)"
            }

            async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
                # First step: search for exact page title
                search_res = await client.get(search_url, headers=headers)
                if search_res.status_code != 200:
                    return f"Wikipedia API returned status {search_res.status_code}."

                search_data = search_res.json()
                if not search_data or len(search_data) < 2 or not search_data[1]:
                    return f"No Wikipedia article found matching '{query}'."

                title = search_data[1][0]
                # Second step: fetch summary for resolved title
                summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title)}"
                sum_res = await client.get(summary_url, headers=headers)

                if sum_res.status_code != 200:
                    return f"Could not retrieve summary for Wikipedia article '{title}'."

                sum_data = sum_res.json()
                extract = sum_data.get("extract")
                description = sum_data.get("description", "")

                if not extract:
                    return f"No detailed text extract available for '{title}'."

                header = f"### {title}" + (f" ({description})" if description else "")
                return f"{header}\n\n{extract}"

        except httpx.TimeoutException:
            return f"Wikipedia query for '{query}' timed out after 6 seconds."
        except Exception as e:
            return f"Wikipedia Error for query '{query}': {str(e)}"
