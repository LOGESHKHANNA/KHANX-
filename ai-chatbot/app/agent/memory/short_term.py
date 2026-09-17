from typing import List, Dict, Any, Optional

class ShortTermMemory:
    """Manages short-term conversation context, sliding window trimming, and summarization."""

    def __init__(self, max_history_turns: int = 8):
        self.max_history_turns = max_history_turns

    def process_messages(
        self,
        messages: List[Dict[str, str]],
        summary_context: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """Trim messages to a reasonable sliding window and prepend summary if available."""
        if not messages:
            return []

        # Keep last (max_history_turns * 2) messages (user + assistant turns)
        max_msgs = self.max_history_turns * 2
        trimmed = messages[-max_msgs:] if len(messages) > max_msgs else messages

        result = []
        if summary_context:
            result.append({
                "role": "system",
                "content": f"Prior Conversation Summary Context:\n{summary_context}"
            })

        for m in trimmed:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role in ("user", "assistant", "system", "tool") and content:
                msg_obj = {"role": role, "content": content}
                if "tool_call_id" in m:
                    msg_obj["tool_call_id"] = m["tool_call_id"]
                if "name" in m:
                    msg_obj["name"] = m["name"]
                if "tool_calls" in m:
                    msg_obj["tool_calls"] = m["tool_calls"]
                result.append(msg_obj)

        return result

    def needs_summarization(self, messages: List[Dict[str, str]], threshold: int = 16) -> bool:
        """Return True if conversation history is long enough to warrant summarization."""
        return len(messages) > threshold

    def summarize_conversation(self, messages: List[Dict[str, str]], groq_client: Any = None) -> Optional[str]:
        """Summarize older conversation turns, preserving goals, decisions, and unresolved tasks.
        
        Keeps the most recent 6 messages intact for the LLM, summarizing everything older.
        Returns None on failure — caller must fall back to the raw sliding window.
        """
        if len(messages) <= 6 or not groq_client:
            return None

        try:
            # Split: older turns to summarize, recent turns to keep verbatim
            older_turns = messages[:-6]
            
            conv_text_parts = []
            for m in older_turns:
                role = m.get("role", "user")
                content = m.get("content", "")
                if role in ("user", "assistant") and content and len(content) > 5:
                    label = "User" if role == "user" else "Assistant"
                    conv_text_parts.append(f"{label}: {content[:400]}")
            
            if not conv_text_parts:
                return None

            conv_text = "\n".join(conv_text_parts)

            summary_prompt = [
                {
                    "role": "system",
                    "content": (
                        "You are a conversation summarizer. Analyze the conversation and produce a concise summary "
                        "covering these exact sections:\n\n"
                        "**Goals:** What the user is trying to accomplish.\n"
                        "**Decisions:** Key choices or conclusions agreed upon.\n"
                        "**Unresolved Tasks:** Outstanding questions or pending follow-ups.\n\n"
                        "Be very concise (3-6 bullet points total). Omit filler. Preserve specific names, values, "
                        "and technical details where important."
                    )
                },
                {
                    "role": "user",
                    "content": f"Summarize this conversation:\n\n{conv_text}"
                }
            ]

            from app.services.groq_retry import call_groq_with_retry
            res = call_groq_with_retry(
                groq_client.chat.completions.create,
                messages=summary_prompt,
                model="groq/compound-mini",
                max_tokens=400
            )
            summary = res.choices[0].message.content.strip()
            return summary if summary else None

        except Exception as e:
            print(f"ShortTermMemory summarization error: {e}")
            return None

