from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class DocumentResponse(BaseModel):
    id: str
    user_id: str
    filename: str
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    uploaded_at: datetime
