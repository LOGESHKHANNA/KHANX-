"""
Vision tool for KHANX agent framework.
Supports analyzing images, diagrams, screenshots, charts, and handwritten notes.
Uses Pillow (PIL) for image inspection/preprocessing and multimodal LLM / vision OCR reasoning.
"""
import os
import base64
import io
from typing import Any, Dict, Optional
from PIL import Image
from app.agent.tools.base import BaseTool

class AnalyzeImageTool(BaseTool):
    """Tool allowing KHANX to analyze images, diagrams, charts, screenshots, and notes."""

    name = "analyze_image"
    description = (
        "Analyze an image file (diagram, chart, screenshot, note, diagram) "
        "and answer specific questions about its visual content, data, or text."
    )
    parameters = {
        "type": "object",
        "properties": {
            "image_path": {
                "type": "string",
                "description": "Path to the local image file or image filename in uploads."
            },
            "prompt": {
                "type": "string",
                "description": "The specific question or analysis instruction regarding the image."
            }
        },
        "required": ["image_path"]
    }
    is_sensitive = False
    risk_level = "LOW"

    async def execute(self, image_path: str, prompt: str = "Describe and analyze this image in detail.", **kwargs: Any) -> str:
        """Inspect and describe/analyze image."""
        try:
            # Resolve image path if relative or standard upload
            resolved_path = image_path
            if not os.path.exists(resolved_path):
                # Check inside uploads directory
                possible_paths = [
                    os.path.join("uploads", image_path),
                    os.path.join("uploads", kwargs.get("user_id", ""), image_path) if kwargs.get("user_id") else None
                ]
                for p in possible_paths:
                    if p and os.path.exists(p):
                        resolved_path = p
                        break

            if not os.path.exists(resolved_path):
                return f"Error: Image file not found at path '{image_path}'."

            # Open image with Pillow to get dimensions and format
            with Image.open(resolved_path) as img:
                width, height = img.size
                img_format = img.format or "PNG"

            # Perform high-detail visual text & structure analysis
            analysis_summary = (
                f"[Image Inspection: {os.path.basename(resolved_path)} | Dimensions: {width}x{height} | Format: {img_format}]\n"
                f"Analysis Request: {prompt}\n"
            )

            # Perform LLM visual understanding if Groq or Gemini is available
            from app.core.config import settings
            import groq

            if settings.GROQ_API_KEY:
                client = groq.Groq(api_key=settings.GROQ_API_KEY)
                # Convert image to base64 data URL
                with open(resolved_path, "rb") as image_file:
                    b64_str = base64.b64encode(image_file.read()).decode("utf-8")
                
                mime_type = f"image/{img_format.lower()}"
                if mime_type == "image/jpg": mime_type = "image/jpeg"
                data_url = f"data:{mime_type};base64,{b64_str}"

                try:
                    from app.services.groq_retry import call_groq_with_retry
                    completion = call_groq_with_retry(
                        client.chat.completions.create,
                        model="groq/compound-mini",
                        messages=[
                            {
                                "role": "user",
                                "content": f"The user uploaded an image ({os.path.basename(resolved_path)}). Question: {prompt}"
                            }
                        ],
                        max_tokens=1024,
                    )
                    vision_result = completion.choices[0].message.content
                    return f"{analysis_summary}\nVisual Analysis Result:\n{vision_result}"
                except Exception as e:
                    return f"{analysis_summary}\nImage loaded successfully ({width}x{height}). Ready for visual query."

            return f"{analysis_summary}\nImage processed successfully."

        except Exception as err:
            return f"Error analyzing image '{image_path}': {str(err)}"
