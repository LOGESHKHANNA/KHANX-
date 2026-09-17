from pydantic import BaseModel
from typing import Optional, List

class CalendarAuthResponse(BaseModel):
    is_connected: bool
    provider: Optional[str] = "google"
    auth_url: Optional[str] = None

class CalendarOAuthCallbackRequest(BaseModel):
    code: str
    provider: Optional[str] = "google"

class AvailabilityRequest(BaseModel):
    date: str
    time_window: Optional[str] = "09:00-17:00"

class CalendarEventCreate(BaseModel):
    title: str
    start_time: str
    end_time: str
    description: Optional[str] = None
    location: Optional[str] = None

class CalendarEventResponse(BaseModel):
    id: str
    title: str
    start_time: str
    end_time: str
    description: Optional[str] = None
    location: Optional[str] = None
    status: str
