/**
 * Supabase Integration Helper for KHANX Chatbot
 * Handles authentication, fallback local auth, profile access, and session management.
 *
 * Usage:
 * 1. Include this file in index.html and login.html
 * 2. Load Supabase JS library via CDN:
 *    <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
 */

let _supabaseClient = null;
let _initPromise = null;  // stores the in-flight initialization promise

function getApiBase() {
    return window.location.protocol === 'file:' ? 'http://127.0.0.1:8000' : '';
}

async function _doInit() {
    try {
        const API_BASE = getApiBase();
        const res = await fetch(API_BASE + '/api/config');
        if (res.ok) {
            const config = await res.json();
            if (config.supabase_url && config.supabase_anon_key && config.supabase_url.startsWith('http')) {
                if (window.supabase && typeof window.supabase.createClient === 'function') {
                    _supabaseClient = window.supabase.createClient(config.supabase_url, config.supabase_anon_key);
                    console.log('[Supabase] Client initialized successfully.');
                } else {
                    console.warn('Supabase JS library not found in window. Falling back to backend endpoints.');
                }
            } else {
                console.warn('Supabase URL or Key missing via API config.');
            }
        }
    } catch (e) {
        console.warn("Could not reach backend API config for Supabase initialization.", e);
    }
    return _supabaseClient;
}

async function getClient() {
    // If already initialized, return immediately
    if (_supabaseClient) return _supabaseClient;
    // If init is in-flight, await the same promise (no double-fetch)
    if (!_initPromise) {
        _initPromise = _doInit();
    }
    return _initPromise;
}

// Auto-initialize Supabase client on script load so it's ready by the time
// DOMContentLoaded fires and handleOAuthRedirect() runs.
if (typeof window !== 'undefined') {
    _initPromise = _doInit();
    _initPromise.catch(e => console.warn('Supabase auto-init error:', e));
}

/**
 * AUTHENTICATION
 */

async function signUp(email, password, name) {
    const client = await getClient();
    if (client) {
        try {
            const { data, error } = await client.auth.signUp({
                email,
                password,
                options: {
                    data: { name: name, username: name }
                }
            });
            if (!error) return { data, error: null };
            console.warn("Supabase SDK signUp failed, trying backend endpoint:", error.message);
        } catch (sdkErr) {
            console.warn("Supabase SDK signUp exception, falling back to backend:", sdkErr);
        }
    }

    // Fallback to Python backend endpoint
    try {
        const API_BASE = getApiBase();
        const res = await fetch(API_BASE + '/api/auth/signup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password, username: name })
        });
        if (!res.ok) {
            const errData = await res.json().catch(() => ({ detail: 'Signup failed.' }));
            return { data: null, error: new Error(errData.detail || 'Signup failed.') };
        }
        const data = await res.json();
        return {
            data: {
                user: data.user,
                session: data.access_token ? { access_token: data.access_token, refresh_token: data.refresh_token } : null
            },
            error: null
        };
    } catch (apiErr) {
        return { data: null, error: new Error('Network error during signup: ' + apiErr.message) };
    }
}

async function signIn(email, password) {
    const client = await getClient();
    if (client) {
        try {
            const { data, error } = await client.auth.signInWithPassword({
                email,
                password
            });
            if (!error && data?.session) return { data, error: null };
            if (error) console.warn("Supabase SDK signIn failed, trying backend endpoint:", error.message);
        } catch (sdkErr) {
            console.warn("Supabase SDK signIn exception, falling back to backend:", sdkErr);
        }
    }

    // Fallback to Python backend endpoint
    try {
        const API_BASE = getApiBase();
        const res = await fetch(API_BASE + '/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });
        if (!res.ok) {
            const errData = await res.json().catch(() => ({ detail: 'Invalid email or password.' }));
            // Handle rate limit / account lockout (429)
            if (res.status === 429) {
                const lockMsg = errData.message || errData.detail || 'Too many login attempts. Please try again later.';
                return { data: null, error: new Error(lockMsg) };
            }
            return { data: null, error: new Error(errData.detail || 'Invalid email or password.') };
        }
        const data = await res.json();
        return {
            data: {
                user: data.user,
                session: { access_token: data.access_token, refresh_token: data.refresh_token }
            },
            error: null
        };
    } catch (apiErr) {
        return { data: null, error: new Error('Network error during login: ' + apiErr.message) };
    }
}

async function signOut() {
    try {
        const client = await getClient();
        if (client) {
            await client.auth.signOut();
        }
    } catch (e) {
        console.warn("Sign out exception ignored:", e);
    }
    return { error: null };
}

async function getCurrentUser() {
    const client = await getClient();
    if (!client) return null;
    try {
        const { data: { user } } = await client.auth.getUser();
        return user;
    } catch (e) {
        return null;
    }
}

async function signInWithOAuth(provider = 'google') {
    const client = await getClient();
    if (!client) {
        return {
            data: null,
            error: new Error('Supabase client is not initialized. Google Sign-In requires active Supabase credentials.')
        };
    }
    
    let redirectUrl;
    if (typeof window !== 'undefined' && window.location) {
        if (window.location.protocol === 'file:') {
            redirectUrl = 'http://127.0.0.1:8000/login';
        } else {
            const origin = window.location.origin.replace(/\/$/, '');
            const path = window.location.pathname.endsWith('.html') ? window.location.pathname : '/login';
            redirectUrl = origin + (path.startsWith('/') ? path : '/' + path);
        }
    } else {
        redirectUrl = 'https://khanx.onrender.com/login';
    }

    try {
        const { data, error } = await client.auth.signInWithOAuth({
            provider: provider,
            options: {
                redirectTo: redirectUrl
            }
        });
        return { data, error };
    } catch (err) {
        return { data: null, error: new Error(err.message || `Failed to authenticate with ${provider}.`) };
    }
}

/**
 * PROFILES
 */

async function getProfile() {
    const user = await getCurrentUser();
    if (!user) return null;

    const client = await getClient();
    if (!client) return null;

    try {
        const { data, error } = await client
            .from('profiles')
            .select('*')
            .eq('id', user.id)
            .single();

        return { data, error };
    } catch (e) {
        return { data: null, error: e };
    }
}

// Export functions to global scope for use in HTML files
window.chatBackend = {
    signUp,
    signIn,
    signInWithOAuth,
    signOut,
    getCurrentUser,
    getProfile,
    getClient
};
