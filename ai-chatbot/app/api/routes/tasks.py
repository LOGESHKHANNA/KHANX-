from fastapi import APIRouter, HTTPException, Depends, Query, Request
from typing import List, Optional
from app.schemas.task import TaskCreate, TaskUpdate, TaskResponse
from app.api.deps import get_current_user
from app.services.supabase_client import get_authed_client
from app.agent.task_manager import task_manager_engine
from app.core.limiter import limiter

router = APIRouter()

@router.get("", response_model=List[TaskResponse])
@router.get("/", response_model=List[TaskResponse])
@limiter.limit("60/minute")
async def list_user_tasks(
    request: Request,
    status: Optional[str] = Query(None, description="Filter tasks by status: 'pending', 'completed', or 'all'"),
    current_user_data = Depends(get_current_user)
):
    """List all tasks belonging strictly to the authenticated user."""
    current_user, token = current_user_data
    db = get_authed_client(token)
    user_id = str(current_user.id)
    tasks = await task_manager_engine.list_tasks(user_id=user_id, status_filter=status, db=db)
    return tasks

@router.post("", response_model=TaskResponse)
@router.post("/", response_model=TaskResponse)
@limiter.limit("30/minute")
async def create_user_task(
    request: Request,
    task_in: TaskCreate,
    current_user_data = Depends(get_current_user)
):
    """Create a new task for the authenticated user."""
    current_user, token = current_user_data
    db = get_authed_client(token)
    user_id = str(current_user.id)
    if not task_in.title or not task_in.title.strip():
        raise HTTPException(status_code=400, detail="Task title is required.")
    
    task = await task_manager_engine.create_task(
        user_id=user_id,
        title=task_in.title,
        description=task_in.description,
        priority=task_in.priority or "medium",
        db=db
    )
    return task

@router.patch("/{task_id}", response_model=TaskResponse)
@limiter.limit("30/minute")
async def update_user_task(
    request: Request,
    task_id: str,
    task_in: TaskUpdate,
    current_user_data = Depends(get_current_user)
):
    """Update a task belonging strictly to the authenticated user."""
    current_user, token = current_user_data
    db = get_authed_client(token)
    user_id = str(current_user.id)
    
    updated = await task_manager_engine.update_task(
        user_id=user_id,
        task_id_or_title=task_id,
        title=task_in.title,
        description=task_in.description,
        status=task_in.status,
        priority=task_in.priority,
        db=db
    )
    if not updated:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    return updated

@router.post("/{task_id}/complete", response_model=TaskResponse)
@limiter.limit("30/minute")
async def complete_user_task(
    request: Request,
    task_id: str,
    current_user_data = Depends(get_current_user)
):
    """Mark a task as completed for the authenticated user."""
    current_user, token = current_user_data
    db = get_authed_client(token)
    user_id = str(current_user.id)
    
    completed = await task_manager_engine.complete_task(
        user_id=user_id,
        task_id_or_title=task_id,
        db=db
    )
    if not completed:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    return completed

@router.delete("/{task_id}")
@limiter.limit("30/minute")
async def delete_user_task(
    request: Request,
    task_id: str,
    current_user_data = Depends(get_current_user)
):
    """Delete a task belonging strictly to the authenticated user."""
    current_user, token = current_user_data
    db = get_authed_client(token)
    user_id = str(current_user.id)
    
    success = await task_manager_engine.delete_task(
        user_id=user_id,
        task_id_or_title=task_id,
        db=db
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    return {"message": f"Task '{task_id}' deleted successfully."}
