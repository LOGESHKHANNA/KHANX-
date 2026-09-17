"""
Email Tools for KHANX agentic framework.

1. DraftEmailTool (`draft_email`):
   - Safe draft creation tool (`is_sensitive = False`).
   - Drafts new emails or prepares replies for user review.
   - Credentials and tokens are NEVER exposed to the LLM or tool arguments.

2. SendEmailTool (`send_email`):
   - Sensitive dispatch tool (`is_sensitive = True`, `risk_level = "HIGH"`).
   - REQUIRES HUMAN-IN-THE-LOOP (HITL) USER APPROVAL before sending.
   - KHANX will NEVER send emails automatically!
"""

from typing import Any, Optional
from app.agent.tools.base import BaseTool
from app.agent.email_manager import email_manager_engine


class DraftEmailTool(BaseTool):
    """Tool for KHANX to draft an email or prepare a reply."""

    name = "draft_email"
    description = (
        "Draft a new email or prepare a reply for user review. "
        "Does NOT send the email. Flow: Draft -> User Approval -> Send."
    )
    parameters = {
        "type": "object",
        "properties": {
            "recipient": {
                "type": "string",
                "description": "Recipient email address (e.g. 'alex@example.com')."
            },
            "subject": {
                "type": "string",
                "description": "Email subject line."
            },
            "body": {
                "type": "string",
                "description": "Body text of the email draft or prepared reply."
            },
            "reply_to_id": {
                "type": "string",
                "description": "Optional thread or message ID if replying to an existing email."
            }
        },
        "required": ["recipient", "subject", "body"]
    }
    is_sensitive = False
    risk_level = "LOW"

    async def execute(
        self,
        recipient: str,
        subject: str,
        body: str,
        reply_to_id: Optional[str] = None,
        db: Optional[Any] = None,
        user_id: Optional[str] = None,
        **kwargs: Any
    ) -> str:
        """Execute email draft creation."""
        if not user_id:
            return "Email drafting unavailable: No authenticated user context."

        try:
            draft = await email_manager_engine.create_draft(
                user_id=user_id,
                recipient=recipient,
                subject=subject,
                body=body,
                reply_to_id=reply_to_id,
                db=db
            )
            return (
                f"📝 **Email Draft Prepared [ID: {draft['id']}]**\n"
                f"- **To**: {draft['recipient']}\n"
                f"- **Subject**: {draft['subject']}\n"
                f"- **Body**:\n```\n{draft['body']}\n```\n"
                f"ℹ️ *Note: This draft has been saved. To send it, please confirm approval when requested.*"
            )
        except Exception as e:
            return f"Failed to prepare email draft: {str(e)}"


class SendEmailTool(BaseTool):
    """Tool to send an email. SENSITIVE: REQUIRES USER APPROVAL!"""

    name = "send_email"
    description = (
        "Send a prepared email draft or message to a recipient. "
        "SENSITIVE ACTION: REQUIRES EXPLICIT USER APPROVAL before sending. NEVER SENDS AUTOMATICALLY."
    )
    parameters = {
        "type": "object",
        "properties": {
            "recipient": {
                "type": "string",
                "description": "Recipient email address."
            },
            "subject": {
                "type": "string",
                "description": "Email subject line."
            },
            "body": {
                "type": "string",
                "description": "Complete email body text to send."
            },
            "draft_id": {
                "type": "string",
                "description": "Optional draft ID to dispatch."
            }
        },
        "required": ["recipient", "subject", "body"]
    }
    # ── HITL SECURITY BARRIER ──────────────────────────────────────────────────
    is_sensitive = True
    risk_level = "HIGH"

    async def execute(
        self,
        recipient: str,
        subject: str,
        body: str,
        draft_id: Optional[str] = None,
        db: Optional[Any] = None,
        user_id: Optional[str] = None,
        **kwargs: Any
    ) -> str:
        """Execute email dispatch after user approval."""
        if not user_id:
            return "Email sending failed: No authenticated user context."

        try:
            sent = await email_manager_engine.send_email(
                user_id=user_id,
                recipient=recipient,
                subject=subject,
                body=body,
                draft_id=draft_id,
                db=db
            )
            return (
                f"🚀 **Email Sent Successfully!** [Message ID: {sent['id']}]\n"
                f"- **To**: {sent['recipient']}\n"
                f"- **Subject**: {sent['subject']}"
            )
        except Exception as e:
            return f"Failed to send email: {str(e)}"
