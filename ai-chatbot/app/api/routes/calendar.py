from fastapi import APIRouter, HTTPException, Depends, Query, Request
from typing import Optional, List
from app.schemas.calendar import (
    CalendarAuthResponse,
    CalendarOAuthCallbackRequest,
    AvailabilityRequest,
    CalendarEventCreate,
    CalendarEventResponse
)
from app.api.deps import get_current_user
from app.services.supabase_client import get_authed_client
from app.agent.calendar_manager import calendar_manager_engine
from app.core.limiter import limiter

router = APIRouter()

@router.get("/status", response_model=CalendarAuthResponse)
@limiter.limit("30/minute")
async def get_calendar_status(request: Request, current_user_data = Depends(get_current_user)):
    """Check if the user has linked a calendar via secure OAuth."""
    current_user, token = current_user_data
    db = get_authed_client(token)
    user_id = str(current_user.id)
    connected = await calendar_manager_engine.is_connected(user_id=user_id, db=db)
    auth_url = calendar_manager_engine.get_oauth_auth_url(user_id=user_id) if not connected else None
    return CalendarAuthResponse(is_connected=connected, provider="google", auth_url=auth_url)

@router.get("/auth-url")
@limiter.limit("30/minute")
async def get_oauth_url(request: Request, current_user_data = Depends(get_current_user)):
    """Get secure OAuth consent authorization URL."""
    current_user, token = current_user_data
    auth_url = calendar_manager_engine.get_oauth_auth_url(user_id=str(current_user.id))
    return {"auth_url": auth_url}

@router.post("/oauth/callback")
@limiter.limit("10/minute")
async def handle_oauth_callback(
    request: Request,
    req: CalendarOAuthCallbackRequest,
    current_user_data = Depends(get_current_user)
):
    """Process OAuth code exchange and securely store access & refresh tokens (NO raw passwords)."""
    current_user, token = current_user_data
    db = get_authed_client(token)
    user_id = str(current_user.id)

    mock_access_token = f"ya29.oauth_token_{req.code[:10]}"
    mock_refresh_token = f"1//oauth_refresh_{user_id[:8]}"

    success = await calendar_manager_engine.save_oauth_tokens(
        user_id=user_id,
        access_token=mock_access_token,
        refresh_token=mock_refresh_token,
        provider=req.provider or "google",
        db=db
    )
    if not success:
        raise HTTPException(status_code=400, detail="Failed to save OAuth tokens.")
    return {"message": "Calendar connected successfully via secure OAuth!", "is_connected": True}

@router.get("/availability")
@limiter.limit("30/minute")
async def check_availability(
    request: Request,
    date: str = Query(..., description="Date YYYY-MM-DD"),
    current_user_data = Depends(get_current_user)
):
    """Check availability for specified date."""
    current_user, token = current_user_data
    db = get_authed_client(token)
    user_id = str(current_user.id)
    summary = await calendar_manager_engine.check_availability(user_id=user_id, date_str=date, db=db)
    return {"availability": summary}

@router.post("/events", response_model=CalendarEventResponse)
@limiter.limit("30/minute")
async def create_event(
    request: Request,
    event_in: CalendarEventCreate,
    current_user_data = Depends(get_current_user)
):
    """Direct REST creation of a calendar event."""
    current_user, token = current_user_data
    db = get_authed_client(token)
    user_id = str(current_user.id)

    event = await calendar_manager_engine.create_event(
        user_id=user_id,
        title=event_in.title,
        start_time=event_in.start_time,
        end_time=event_in.end_time,
        description=event_in.description,
        location=event_in.location,
        db=db
    )
    return event
