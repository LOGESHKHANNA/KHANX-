"""
Calendar Tools for KHANX agentic framework.

1. CalendarAvailabilityTool (`check_calendar_availability`):
   - Safe read operation (`is_sensitive = False`).
   - Checks user's open slots and schedule conflicts.

2. CreateCalendarEventTool (`create_calendar_event`):
   - Sensitive mutation operation (`is_sensitive = True`, `risk_level = "MEDIUM"`).
   - REQUIRES HUMAN-IN-THE-LOOP (HITL) USER APPROVAL before executing.
"""

from typing import Any, Optional
from app.agent.tools.base import BaseTool
from app.agent.calendar_manager import calendar_manager_engine


class CalendarAvailabilityTool(BaseTool):
    """Tool to check calendar availability for KHANX."""

    name = "check_calendar_availability"
    description = (
        "Check user's calendar availability, open time slots, or scheduled events for a specific date or time window."
    )
    parameters = {
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "Date to check availability for (e.g. 'YYYY-MM-DD' or 'today', 'tomorrow')."
            },
            "start_time": {
                "type": "string",
                "description": "Optional start time window (e.g. '09:00')."
            },
            "end_time": {
                "type": "string",
                "description": "Optional end time window (e.g. '17:00')."
            }
        },
        "required": ["date"]
    }
    is_sensitive = False
    risk_level = "LOW"

    async def execute(
        self,
        date: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        db: Optional[Any] = None,
        user_id: Optional[str] = None,
        **kwargs: Any
    ) -> str:
        """Check user availability."""
        if not user_id:
            return "Calendar unavailable: No authenticated user context."

        try:
            return await calendar_manager_engine.check_availability(
                user_id=user_id,
                date_str=date,
                start_time=start_time,
                end_time=end_time,
                db=db
            )
        except Exception as e:
            return f"[Calendar temporary warning: {str(e)}. Proceeding with standard response.]"


class CreateCalendarEventTool(BaseTool):
    """Tool to create calendar events. SENSITIVE: REQUIRES USER APPROVAL!"""

    name = "create_calendar_event"
    description = (
        "Schedule or create a new event/meeting on the user's connected calendar. "
        "REQUIRES USER APPROVAL before being saved to calendar."
    )
    parameters = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Event or meeting title."
            },
            "start_time": {
                "type": "string",
                "description": "Start date and time (e.g. '2026-08-25T10:00:00')."
            },
            "end_time": {
                "type": "string",
                "description": "End date and time (e.g. '2026-08-25T11:00:00')."
            },
            "description": {
                "type": "string",
                "description": "Optional event details, agenda, or notes."
            },
            "location": {
                "type": "string",
                "description": "Optional meeting location or video call link."
            }
        },
        "required": ["title", "start_time", "end_time"]
    }
    # ── HITL SECURITY BARRIER ──────────────────────────────────────────────────
    is_sensitive = True
    risk_level = "MEDIUM"

    async def execute(
        self,
        title: str,
        start_time: str,
        end_time: str,
        description: Optional[str] = None,
        location: Optional[str] = None,
        db: Optional[Any] = None,
        user_id: Optional[str] = None,
        **kwargs: Any
    ) -> str:
        """Execute calendar event creation after approval."""
        if not user_id:
            return "Calendar creation failed: No authenticated user context."

        try:
            event = await calendar_manager_engine.create_event(
                user_id=user_id,
                title=title,
                start_time=start_time,
                end_time=end_time,
                description=description,
                location=location,
                db=db
            )
            return (
                f"✅ Calendar Event Scheduled successfully!\n"
                f"- **Title**: {event['title']}\n"
                f"- **Time**: {event['start_time']} to {event['end_time']}\n"
                f"- **Details**: {event['description'] or 'None'}"
            )
        except Exception as e:
            return f"Failed to create calendar event: {str(e)}"
