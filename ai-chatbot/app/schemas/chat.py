from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class ChatSessionCreate(BaseModel):
    title: Optional[str] = "New Chat"

class ChatSessionResponse(BaseModel):
    id: str
    user_id: str
    title: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime] = None

class ChatMessageCreate(BaseModel):
    user_message: str
    mode: Optional[str] = "chat"
    images: Optional[List[str]] = None  # Base64 strings or image URLs


class ChatMessageResponse(BaseModel):
    id: str
    session_id: str
    user_message: str
    assistant_message: str
    created_at: datetime
