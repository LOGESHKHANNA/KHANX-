import urllib.parse
from typing import Any
from app.agent.tools.base import BaseTool

class GenerateImageTool(BaseTool):
    """Tool allowing KHANX to generate images from user text prompts."""

    name = "generate_image"
    description = (
        "Generate an image based on a descriptive text prompt. "
        "Returns a markdown image string containing the generated image."
    )
    parameters = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "A highly detailed description of the image to generate."
            }
        },
        "required": ["prompt"]
    }
    is_sensitive = False
    risk_level = "LOW"

    async def execute(self, prompt: str, **kwargs: Any) -> str:
        """Generate image and return markdown."""
        encoded_prompt = urllib.parse.quote(prompt)
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true"
        return f"![Generated Image]({image_url})\n\n*(Image generated for prompt: {prompt})*"
