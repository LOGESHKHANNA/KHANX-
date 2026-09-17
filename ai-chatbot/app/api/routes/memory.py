from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Dict, Any
from app.schemas.memory import MemoryFactCreate, MemoryFactResponse, MemoryOverviewResponse
from app.services.supabase_client import get_authed_client
from app.api.deps import get_current_user
from app.agent.memory.manager import memory_manager
from app.core.limiter import limiter

router = APIRouter()

@router.get("", response_model=MemoryOverviewResponse)
@router.get("/", response_model=MemoryOverviewResponse)
@limiter.limit("60/minute")
async def get_user_memories(request: Request, current_user_data=Depends(get_current_user)):
    """View all semantic & episodic memories for the authenticated user."""
    current_user, token = current_user_data
    try:
        db = get_authed_client(token)
        res = await memory_manager.get_user_memories(str(current_user.id), db=db)
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("", response_model=Dict[str, Any])
@router.post("/", response_model=Dict[str, Any])
@limiter.limit("30/minute")
async def add_user_memory(request: Request, payload: MemoryFactCreate, current_user_data=Depends(get_current_user)):
    """Store or update a semantic fact/preference for the authenticated user."""
    current_user, token = current_user_data
    try:
        db = get_authed_client(token)
        res = await memory_manager.add_semantic_fact(
            user_id=str(current_user.id),
            key=payload.key,
            value=payload.value,
            category=payload.category or "preference",
            db=db
        )
        return res
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/clear")
@limiter.limit("10/minute")
async def clear_all_memories(request: Request, current_user_data=Depends(get_current_user)):
    """Clear all memories (semantic & episodic) for the authenticated user."""
    current_user, token = current_user_data
    try:
        db = get_authed_client(token)
        success = await memory_manager.clear_all_user_memories(str(current_user.id), db=db)
        return {"success": success, "message": "All user memories successfully cleared."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/sessions/{session_id}")
@limiter.limit("30/minute")
async def delete_session_memory(request: Request, session_id: str, current_user_data=Depends(get_current_user)):
    """Delete episodic summary for a specific chat session."""
    current_user, token = current_user_data
    try:
        db = get_authed_client(token)
        success = await memory_manager.delete_session_episodic(str(current_user.id), session_id, db=db)
        return {"success": success, "message": f"Episodic memory for session '{session_id}' cleared."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{key}")
@limiter.limit("30/minute")
async def delete_user_memory(request: Request, key: str, current_user_data=Depends(get_current_user)):
    """Delete a specific semantic memory fact by key or ID."""
    current_user, token = current_user_data
    try:
        db = get_authed_client(token)
        success = await memory_manager.delete_semantic_fact(str(current_user.id), key, db=db)
        if not success:
            raise HTTPException(status_code=404, detail=f"Memory key '{key}' not found.")
        return {"success": True, "message": f"Memory '{key}' deleted."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
