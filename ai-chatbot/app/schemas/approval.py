from pydantic import BaseModel
from typing import Dict, Any, List, Optional

class ActionApproveRequest(BaseModel):
    modified_arguments: Optional[Dict[str, Any]] = None

class ActionApprovalResponse(BaseModel):
    action_id: str
    user_id: str
    session_id: Optional[str] = None
    action_type: str
    tool_name: str
    arguments: Dict[str, Any]
    explanation: str
    risk_level: str
    status: str
    created_at: str
    updated_at: str
    expires_at: str
    execution_result: Optional[str] = None

class PendingActionsResponse(BaseModel):
    user_id: str
    pending_actions: List[Dict[str, Any]]
