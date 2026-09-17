import httpx
import re
from typing import Any, Dict
from urllib.parse import quote_plus
from app.agent.tools.base import BaseTool

class WebSearchTool(BaseTool):
    """Tool for fetching real-time web search results."""
    name = "web_search"
    description = "Search the web for current events, recent news, updates, or web information not in local context."
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search terms to look up on the web."
            }
        },
        "required": ["query"]
    }

    async def execute(self, query: str, **kwargs: Any) -> str:
        """Execute DuckDuckGo web search via async HTTP."""
        try:
            encoded_query = quote_plus(query)
            url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }

            async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code != 200:
                    return f"[Web search unavailable (HTTP status {resp.status_code}). Proceeding with standard AI response.]"

                html = resp.text
                # Extract snippets from DuckDuckGo HTML
                snippets = re.findall(r'<a class="result__snippet[^">]*>(.*?)</a>', html, re.DOTALL)
                titles = re.findall(r'<a class="result__url[^">]*>(.*?)</a>', html, re.DOTALL)

                results = []
                for i, snip in enumerate(snippets[:4]):
                    clean_snip = re.sub(r'<[^>]+>', '', snip).strip()
                    title = re.sub(r'<[^>]+>', '', titles[i]).strip() if i < len(titles) else f"Result {i+1}"
                    if clean_snip:
                        results.append(f"• Web Source: [{title}]\n  Snippet: {clean_snip}")

                if not results:
                    return f"[No web search results found for '{query}'. Proceeding with standard AI response.]"

                return "\n\n".join(results)

        except httpx.TimeoutException:
            return f"[Web search timed out. Proceeding with standard AI response.]"
        except Exception as e:
            return f"[Web search temporary error: {str(e)}. Proceeding with standard AI response.]"

