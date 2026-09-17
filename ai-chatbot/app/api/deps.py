from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.supabase_client import supabase, get_authed_client
from typing import Tuple

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify the JWT and return (user, token) so routes can build an authed Supabase client."""
    try:
        token = credentials.credentials
        # We pass the JWT token to Supabase to verify it
        response = supabase.auth.get_user(token)
        if not response or not response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return response.user, token
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


def ensure_profile_exists(user, token: str) -> dict:
    """
    Ensures that a record for user.id exists in the profiles table.
    Prevents foreign-key constraint failures on chat_sessions, documents, tasks, etc.
    Handles existing users, new email users, and Google/OAuth users safely.
    """
    auth_user_id = str(user.id)
    user_email = getattr(user, "email", None) or f"{auth_user_id}@user.com"

    meta_name = None
    if getattr(user, "user_metadata", None):
        meta_name = (
            user.user_metadata.get("username")
            or user.user_metadata.get("name")
            or user.user_metadata.get("full_name")
        )
    if not meta_name and getattr(user, "email", None):
        meta_name = user.email.split("@")[0]

    print(f"=== AUTH USER ID: {auth_user_id} ===")

    # 1. Check if profile already exists in DB for this exact auth_user_id
    profile_exists = False
    existing_profile = None

    try:
        authed_db = get_authed_client(token)
        res = authed_db.table("profiles").select("*").eq("id", auth_user_id).execute()
        if res.data and len(res.data) > 0:
            profile_exists = True
            existing_profile = res.data[0]
    except Exception as e:
        print(f"[Profile Check] Authed select error for user {auth_user_id}: {e}")

    if not profile_exists:
        try:
            res_anon = supabase.table("profiles").select("*").eq("id", auth_user_id).execute()
            if res_anon.data and len(res_anon.data) > 0:
                profile_exists = True
                existing_profile = res_anon.data[0]
        except Exception as e:
            print(f"[Profile Check] Anon select error for user {auth_user_id}: {e}")

    print(f"=== PROFILE EXISTS: {profile_exists} ===")

    if profile_exists and existing_profile:
        print(f"=== PROFILE ID: {existing_profile.get('id')} ===")
        return existing_profile

    # 2. Profile does NOT exist — create/upsert it using auth_user_id (matching auth.users.id)
    payload = {
        "id": auth_user_id,
        "email": user_email,
        "username": meta_name
    }

    created = False
    last_error = None

    # Try 1: Authed client insert first (satisfies RLS FOR INSERT WITH CHECK (auth.uid() = id))
    try:
        authed_db = get_authed_client(token)
        ins_res = authed_db.table("profiles").insert(payload).execute()
        if ins_res.data and len(ins_res.data) > 0:
            created = True
            existing_profile = ins_res.data[0]
    except Exception as e:
        last_error = e
        print(f"[Profile Insert Error] Authed client insert failed for ID {auth_user_id}: {e}")

    # Try 2: Authed client upsert fallback
    if not created:
        try:
            authed_db = get_authed_client(token)
            upsert_res = authed_db.table("profiles").upsert(payload, on_conflict="id").execute()
            if upsert_res.data and len(upsert_res.data) > 0:
                created = True
                existing_profile = upsert_res.data[0]
        except Exception as e:
            last_error = e
            print(f"[Profile Upsert Error] Authed client upsert failed for ID {auth_user_id}: {e}")
            if "profiles_email_key" in str(e) or "unique constraint" in str(e).lower():
                fallback_email = f"{auth_user_id[:8]}_{user_email}"
                payload["email"] = fallback_email
                try:
                    authed_db = get_authed_client(token)
                    upsert_res2 = authed_db.table("profiles").upsert(payload, on_conflict="id").execute()
                    if upsert_res2.data and len(upsert_res2.data) > 0:
                        created = True
                        existing_profile = upsert_res2.data[0]
                except Exception as e2:
                    last_error = e2
                    print(f"[Profile Upsert Error] Authed client fallback email upsert failed for ID {auth_user_id}: {e2}")

    # Try 3: Global client upsert fallback
    if not created:
        try:
            res_global = supabase.table("profiles").upsert(payload, on_conflict="id").execute()
            if res_global.data and len(res_global.data) > 0:
                created = True
                existing_profile = res_global.data[0]
        except Exception as e:
            last_error = e
            print(f"[Profile Upsert Error] Global client upsert failed for ID {auth_user_id}: {e}")

    # 3. VERIFY that the profile row NOW EXISTS in profiles table
    verification_res = existing_profile
    
    # Always attempt a database query verification if insert/upsert didn't return a record directly
    try:
        authed_db = get_authed_client(token)
        v_res = authed_db.table("profiles").select("*").eq("id", auth_user_id).execute()
        if v_res.data and len(v_res.data) > 0:
            verification_res = v_res.data[0]
    except Exception as e:
        print(f"[Profile Verification Error] Authed select failed: {e}")

    if not verification_res:
        try:
            v_res_anon = supabase.table("profiles").select("*").eq("id", auth_user_id).execute()
            if v_res_anon.data and len(v_res_anon.data) > 0:
                verification_res = v_res_anon.data[0]
        except Exception as e:
            print(f"[Profile Verification Error] Anon select failed: {e}")

    if verification_res:
        print(f"=== PROFILE ID: {verification_res.get('id')} ===")
        return verification_res

    # If profile creation and verification failed, raise a clear HTTP 400 error with detailed log
    err_detail = f"Unable to verify or create user profile in database for ID {auth_user_id}."
    if last_error:
        err_detail += f" Error detail: {str(last_error)}"
    print(f"[CRITICAL ERROR] {err_detail}")
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=err_detail
    )

