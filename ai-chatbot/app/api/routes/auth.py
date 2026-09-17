from fastapi import APIRouter, HTTPException, Depends, Request
from app.schemas.user import UserCreate, UserLogin, UserResponse, UserProfileUpdate
from app.services.supabase_client import supabase, get_authed_client
from app.api.deps import get_current_user, ensure_profile_exists
from app.core.limiter import limiter
from pydantic import BaseModel

router = APIRouter()

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    user: UserResponse

@router.post("/signup", response_model=TokenResponse)
@limiter.limit("10/hour")
def signup(request: Request, user_data: UserCreate):
    """User signup endpoint with rate limiting to prevent spam registration."""
    try:
        response = supabase.auth.sign_up({
            "email": user_data.email,
            "password": user_data.password,
            "options": {
                "data": {
                    "username": user_data.username
                }
            }
        })
        if not response.user:
            raise HTTPException(status_code=400, detail="Signup failed.")
        
        if not response.session:
            return {
                "access_token": "",
                "refresh_token": "",
                "user": {
                    "id": str(response.user.id),
                    "email": response.user.email,
                    "username": user_data.username
                },
                "message": "User created. Please check your email to confirm your account."
            }
            
        return {
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
            "user": {
                "id": response.user.id,
                "email": response.user.email,
                "username": user_data.username
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
def login(request: Request, user_data: UserLogin):
    """
    User login endpoint with multi-layer brute-force protection:
    1. slowapi per-IP rate limit (5/min)
    2. Per-email consecutive failure lockout (5 failures → 15 min lock)
    3. Per-IP consecutive failure lockout (10 failures → 30 min lock)
    """
    from app.core.login_security import login_tracker
    from slowapi.util import get_remote_address

    client_ip = get_remote_address(request)
    email = user_data.email.lower().strip()

    # ── Layer 2: Check account/IP lockout ──────────────────────────────────
    is_locked, lock_msg, retry_after = login_tracker.check_lockout(email, client_ip)
    if is_locked:
        raise HTTPException(
            status_code=429,
            detail=lock_msg,
            headers={"Retry-After": str(retry_after)},
        )

    # ── Authenticate via Supabase ──────────────────────────────────────────
    try:
        response = supabase.auth.sign_in_with_password({
            "email": user_data.email,
            "password": user_data.password
        })
        if not response.session:
            # Supabase returned no session — count as failure
            login_tracker.record_failure(email, client_ip)
            raise HTTPException(status_code=400, detail="Login failed.")

        # ── Success: reset all failure counters ────────────────────────────
        login_tracker.record_success(email, client_ip)

        username = response.user.user_metadata.get("username") if response.user.user_metadata else None

        return {
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
            "user": {
                "id": response.user.id,
                "email": response.user.email,
                "username": username
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        # ── Auth failure: record and return generic message ────────────────
        newly_locked, lock_msg, retry_after = login_tracker.record_failure(email, client_ip)
        if newly_locked:
            raise HTTPException(
                status_code=429,
                detail=lock_msg,
                headers={"Retry-After": str(retry_after)},
            )
        raise HTTPException(status_code=401, detail="Invalid email or password.")

@router.get("/profile", response_model=UserResponse)
@router.get("/me", response_model=UserResponse)
@limiter.limit("60/minute")
def get_profile(request: Request, current_user_data = Depends(get_current_user)):
    """Fetch user profile from database, ensuring profile record exists."""
    current_user, token = current_user_data
    prof = ensure_profile_exists(current_user, token)
    return {
        "id": prof["id"],
        "email": prof["email"],
        "username": prof.get("username")
    }

@router.put("/profile", response_model=UserResponse)
@router.post("/profile", response_model=UserResponse)
@limiter.limit("30/minute")
def update_profile(request: Request, profile_data: UserProfileUpdate, current_user_data = Depends(get_current_user)):
    """Update user's display name / username in profiles table and auth metadata."""
    current_user, token = current_user_data
    user_id_str = str(current_user.id)
    clean_username = profile_data.username.strip()
    if not clean_username:
        raise HTTPException(status_code=400, detail="Username cannot be empty.")
    
    try:
        try:
            authed_db = get_authed_client(token)
            authed_db.table("profiles").upsert({
                "id": user_id_str,
                "email": current_user.email or f"{user_id_str}@user.com",
                "username": clean_username
            }, on_conflict="id").execute()
        except Exception:
            supabase.table("profiles").upsert({
                "id": user_id_str,
                "email": current_user.email or f"{user_id_str}@user.com",
                "username": clean_username
            }, on_conflict="id").execute()

        try:
            supabase.auth.admin.update_user_by_id(user_id_str, {
                "user_metadata": {"username": clean_username, "name": clean_username}
            })
        except Exception as meta_err:
            print(f"User metadata update note: {meta_err}")

        return {
            "id": user_id_str,
            "email": current_user.email or "",
            "username": clean_username
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating profile: {e}")
        raise HTTPException(status_code=400, detail=f"Could not update profile: {str(e)}")

@router.post("/logout")
@limiter.limit("30/minute")
def logout(request: Request, current_user_data = Depends(get_current_user)):
    """
    Logout endpoint — revokes user session server-side using current authenticated client context.
    """
    current_user, token = current_user_data
    try:
        from app.services.supabase_client import get_authed_client, invalidate_client_cache
        authed_db = get_authed_client(token)
        authed_db.auth.sign_out()
        invalidate_client_cache(token)
        return {"message": "Logged out successfully"}
    except Exception as e:
        print(f"Server-side signout note: {e}")
        return {"message": "Logged out"}

