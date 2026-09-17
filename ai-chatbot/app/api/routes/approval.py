from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Dict, Any, Optional
from app.schemas.approval import ActionApproveRequest, ActionApprovalResponse, PendingActionsResponse
from app.services.supabase_client import get_authed_client
from app.api.deps import get_current_user
from app.agent.approval import approval_manager
from app.core.limiter import limiter

router = APIRouter()

@router.get("/pending", response_model=PendingActionsResponse)
@limiter.limit("60/minute")
async def get_pending_actions(request: Request, current_user_data=Depends(get_current_user)):
    """Fetch active pending action proposals requiring human approval for authenticated user."""
    current_user, token = current_user_data
    try:
        db = get_authed_client(token)
        pending = await approval_manager.get_pending_actions(str(current_user.id), db=db)
        return {
            "user_id": str(current_user.id),
            "pending_actions": pending
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{action_id}/approve", response_model=Dict[str, Any])
@limiter.limit("30/minute")
async def approve_action(
    request: Request,
    action_id: str,
    payload: Optional[ActionApproveRequest] = None,
    current_user_data=Depends(get_current_user)
):
    """Approve a proposed action (optionally passing modified_arguments)."""
    current_user, token = current_user_data
    try:
        db = get_authed_client(token)
        mod_args = payload.modified_arguments if payload else None
        res = await approval_manager.approve_action(
            action_id=action_id,
            user_id=str(current_user.id),
            modified_arguments=mod_args,
            db=db
        )
        return res.to_dict()
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{action_id}/reject", response_model=Dict[str, Any])
@limiter.limit("30/minute")
async def reject_action(request: Request, action_id: str, current_user_data=Depends(get_current_user)):
    """Reject a proposed action."""
    current_user, token = current_user_data
    try:
        db = get_authed_client(token)
        res = await approval_manager.reject_action(
            action_id=action_id,
            user_id=str(current_user.id),
            db=db
        )
        return res.to_dict()
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{action_id}/execute", response_model=Dict[str, Any])
@limiter.limit("30/minute")
async def execute_approved_action(request: Request, action_id: str, current_user_data=Depends(get_current_user)):
    """Execute an approved action after backend enforcement checks."""
    current_user, token = current_user_data
    try:
        db = get_authed_client(token)
        res = await approval_manager.execute_approved_action(
            action_id=action_id,
            user_id=str(current_user.id),
            db=db
        )
        return res
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
