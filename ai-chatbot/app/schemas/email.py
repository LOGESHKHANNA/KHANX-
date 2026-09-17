from pydantic import BaseModel
from typing import Optional, List

class EmailAuthResponse(BaseModel):
    is_connected: bool
    provider: Optional[str] = "google_gmail"
    auth_url: Optional[str] = None

class EmailOAuthCallbackRequest(BaseModel):
    code: str
    provider: Optional[str] = "google_gmail"

class EmailDraftCreate(BaseModel):
    recipient: str
    subject: str
    body: str
    reply_to_id: Optional[str] = None

class EmailDraftResponse(BaseModel):
    id: str
    user_id: str
    recipient: str
    subject: str
    body: str
    reply_to_id: Optional[str] = None
    status: str
    created_at: str

class SendEmailRequest(BaseModel):
    draft_id: Optional[str] = None
    recipient: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
