from supabase import create_client, Client
from app.core.config import settings
from functools import lru_cache

def get_supabase_client() -> Client:
    """Create a new unauthenticated Supabase client instance."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

# Global singleton anon client — used for public auth verification
supabase: Client = get_supabase_client()

@lru_cache(maxsize=128)
def _cached_authed_client(user_token: str) -> Client:
    """
    Pooled Supabase client instances cached per user JWT token.
    Prevents expensive HTTP client initialization on every single request.
    """
    try:
        from supabase.lib.client_options import ClientOptions
        headers = {"Authorization": f"Bearer {user_token}"}
        client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY, options=ClientOptions(headers=headers))
    except Exception:
        client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    
    try:
        client.postgrest.auth(user_token)
    except Exception:
        pass
    return client

def get_authed_client(user_token: str) -> Client:
    """
    Retrieves a connection-pooled Supabase client for the given JWT token.
    Sets auth.uid() correctly for RLS policies.
    """
    if not user_token:
        return supabase
    return _cached_authed_client(user_token)

def invalidate_client_cache(user_token: str = None):
    """Clear cached authed client instances (e.g. upon user logout)."""
    _cached_authed_client.cache_clear()
