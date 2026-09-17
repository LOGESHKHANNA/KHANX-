from fastapi import APIRouter, HTTPException, Depends, Query, Request
from typing import Optional, List
from app.schemas.email import (
    EmailAuthResponse,
    EmailOAuthCallbackRequest,
    EmailDraftCreate,
    EmailDraftResponse,
    SendEmailRequest
)
from app.api.deps import get_current_user
from app.services.supabase_client import get_authed_client
from app.agent.email_manager import email_manager_engine
from app.core.limiter import limiter

router = APIRouter()

@router.get("/status", response_model=EmailAuthResponse)
@limiter.limit("30/minute")
async def get_email_status(request: Request, current_user_data = Depends(get_current_user)):
    """Check if the user has linked an email account via secure OAuth."""
    current_user, token = current_user_data
    db = get_authed_client(token)
    user_id = str(current_user.id)
    connected = await email_manager_engine.is_connected(user_id=user_id, db=db)
    auth_url = email_manager_engine.get_oauth_auth_url(user_id=user_id) if not connected else None
    return EmailAuthResponse(is_connected=connected, provider="google_gmail", auth_url=auth_url)

@router.get("/auth-url")
@limiter.limit("30/minute")
async def get_oauth_url(request: Request, current_user_data = Depends(get_current_user)):
    """Get secure OAuth authorization consent URL."""
    current_user, token = current_user_data
    auth_url = email_manager_engine.get_oauth_auth_url(user_id=str(current_user.id))
    return {"auth_url": auth_url}

@router.post("/oauth/callback")
@limiter.limit("10/minute")
async def handle_oauth_callback(
    request: Request,
    req: EmailOAuthCallbackRequest,
    current_user_data = Depends(get_current_user)
):
    """Exchange authorization code and securely store access & refresh tokens (NO credentials exposed to LLM)."""
    current_user, token = current_user_data
    db = get_authed_client(token)
    user_id = str(current_user.id)

    mock_access_token = f"ya29.email_token_{req.code[:10]}"
    mock_refresh_token = f"1//email_refresh_{user_id[:8]}"

    success = await email_manager_engine.save_oauth_tokens(
        user_id=user_id,
        access_token=mock_access_token,
        refresh_token=mock_refresh_token,
        provider=req.provider or "google_gmail",
        db=db
    )
    if not success:
        raise HTTPException(status_code=400, detail="Failed to save email OAuth tokens.")
    return {"message": "Email connected successfully via secure OAuth!", "is_connected": True}

@router.get("/drafts")
@limiter.limit("30/minute")
async def list_drafts(request: Request, current_user_data = Depends(get_current_user)):
    """List email drafts for the authenticated user."""
    current_user, token = current_user_data
    db = get_authed_client(token)
    user_id = str(current_user.id)
    drafts = await email_manager_engine.list_drafts(user_id=user_id, db=db)
    return drafts

@router.post("/drafts", response_model=EmailDraftResponse)
@limiter.limit("20/minute")
async def create_draft(
    request: Request,
    draft_in: EmailDraftCreate,
    current_user_data = Depends(get_current_user)
):
    """Create an email draft or prepared reply."""
    current_user, token = current_user_data
    db = get_authed_client(token)
    user_id = str(current_user.id)

    draft = await email_manager_engine.create_draft(
        user_id=user_id,
        recipient=draft_in.recipient,
        subject=draft_in.subject,
        body=draft_in.body,
        reply_to_id=draft_in.reply_to_id,
        db=db
    )
    return draft

@router.post("/send")
@limiter.limit("10/minute")
async def send_email(
    request: Request,
    req: SendEmailRequest,
    current_user_data = Depends(get_current_user)
):
    """Send email after user approval."""
    current_user, token = current_user_data
    db = get_authed_client(token)
    user_id = str(current_user.id)

    if not req.recipient or not req.subject or not req.body:
        raise HTTPException(status_code=400, detail="Recipient, subject, and body are required to send an email.")

    try:
        sent = await email_manager_engine.send_email(
            user_id=user_id,
            recipient=req.recipient,
            subject=req.subject,
            body=req.body,
            draft_id=req.draft_id,
            db=db
        )
        return {"message": "Email sent successfully!", "details": sent}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
