from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class MemoryFactCreate(BaseModel):
    key: str
    value: str
    category: Optional[str] = "preference"

class MemoryFactResponse(BaseModel):
    id: Optional[str] = None
    user_id: str
    key: str
    value: str
    category: Optional[str] = "preference"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class MemoryOverviewResponse(BaseModel):
    user_id: str
    semantic_memories: List[Dict[str, Any]]
    episodic_summaries: List[Dict[str, Any]]
