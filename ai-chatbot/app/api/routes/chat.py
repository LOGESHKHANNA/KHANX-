from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
import json
import time
from datetime import datetime, timezone
from app.schemas.chat import ChatSessionCreate, ChatSessionResponse, ChatMessageCreate, ChatMessageResponse
from app.services.supabase_client import supabase, get_authed_client
from app.api.deps import get_current_user, ensure_profile_exists
from app.core.config import settings
from app.core.limiter import limiter
from app.agent.orchestrator import agent_orchestrator
from app.services.groq_retry import call_groq_with_retry
import groq

router = APIRouter()

# Initialize Groq client conditionally
groq_client = groq.Groq(api_key=settings.GROQ_API_KEY) if settings.GROQ_API_KEY else None

KHANNAX_SYSTEM_PROMPT = """You are KHANNAX, an advanced, highly intelligent conversational AI assistant created by Logesh Khanna. Your answers are clear, direct, comprehensive, useful, and naturally structured (like ChatGPT)."""

# ── SSE headers ───────────────────────────────────────────────────────────────
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}

# ── RAG Cache Storage (Distributed Redis + Memory Fallback) ───────────────────
from app.services.cache_service import cache_service
_RAG_CACHE_TTL = 300  # 5 minutes in seconds

def clear_rag_cache(user_id: Optional[str] = None):
    """Clear RAG context cache for a user or globally when documents are updated."""
    if user_id:
        cache_service.clear_pattern(f"rag:{user_id}:")
    else:
        cache_service.clear_pattern("rag:")



def _generate_title_from_text(user_text: str) -> str:
    """Fast regex/truncation title fallback."""
    cleaned = user_text.strip().replace("\n", " ").replace("\r", "")
    if not cleaned:
        return "New Chat"
    words = [w for w in cleaned.split() if w]
    if len(words) <= 5:
        title = " ".join(words)
    else:
        title = " ".join(words[:5])
    if len(title) > 40:
        title = title[:37].rstrip() + "..."
    return title.capitalize()


def _generate_ai_title(user_text: str) -> str:
    """Auto-summarize concise 3-5 word session title using Groq LLM with fast fallback."""
    if not user_text or not user_text.strip():
        return "New Chat"
    if groq_client:
        try:
            res = call_groq_with_retry(
                groq_client.chat.completions.create,
                messages=[
                    {"role": "system", "content": "Generate a concise 3 to 5 word title summarizing the following message topic. Return ONLY the raw title text with no quotation marks, no punctuation, and no extra words."},
                    {"role": "user", "content": user_text[:1000]}
                ],
                model="groq/compound-mini",
                max_tokens=20,
                temperature=0.3
            )
            title = res.choices[0].message.content.strip().strip('"').strip("'")
            if title and len(title) <= 45:
                return title.capitalize()
        except Exception as e:
            print(f"AI title summarizer warning: {e}")
    return _generate_title_from_text(user_text)


def _maybe_auto_title(db, session_id: str, user_message: str):
    """Auto-generate session title if current title is default ('New Chat' or empty)."""
    try:
        session_res = db.table("chat_sessions").select("title").eq("id", session_id).limit(1).execute()
        if session_res.data:
            current_title = session_res.data[0].get("title", "")
            if not current_title or current_title.strip() in ("New Chat", "Untitled", "new chat"):
                new_title = _generate_ai_title(user_message)
                db.table("chat_sessions").update({
                    "title": new_title,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }).eq("id", session_id).execute()
                print(f"Auto-summarized title for session '{session_id}': {new_title}")
    except Exception as err:
        print(f"Auto-title warning: {err}")


# ── Guest / Unauthenticated Chat ─────────────────────────────────────────────
class GuestChatRequest(BaseModel):
    messages: List[dict]

@router.post("")
@router.post("/")
@router.post("/rag")
@limiter.limit("20/minute")
def guest_chat(request: Request, chat_req: GuestChatRequest):
    """Non-streaming unauthenticated chat — used as fallback."""
    if "rag" in request.url.path:
        return {"reply": "RAG (Document search) requires you to be logged in. Please sign in!"}
    if not groq_client:
        return {"reply": "GROQ_API_KEY not set. Set it in .env to enable AI responses."}
    try:
        messages = [{"role": "system", "content": KHANNAX_SYSTEM_PROMPT}]
        recent_messages = chat_req.messages[-8:] if len(chat_req.messages) > 8 else chat_req.messages
        for m in recent_messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role in ("user", "assistant", "system") and content:
                messages.append({"role": role, "content": str(content)[:50000]})
        chat_completion = call_groq_with_retry(
            groq_client.chat.completions.create,
            messages=messages,
            model="groq/compound-mini",
            max_tokens=2048,
        )
        return {"reply": chat_completion.choices[0].message.content}
    except Exception as e:
        print(f"Groq API error: {e}")
        return {"reply": "Error generating response from AI. Please try again."}


@router.post("/stream")
@limiter.limit("20/minute")
async def chat_stream(
    request: Request,
    chat_req: GuestChatRequest,
    current_user_data=Depends(get_current_user)
):
    """Streaming chat endpoint (SSE) requiring valid Supabase JWT authentication."""
    current_user, token = current_user_data
    if not groq_client:
        async def no_key():
            yield f"data: {json.dumps({'text': 'GROQ_API_KEY not configured.'})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(no_key(), media_type="text/event-stream", headers=SSE_HEADERS)

    messages = chat_req.messages[-8:] if len(chat_req.messages) > 8 else chat_req.messages
    return StreamingResponse(
        agent_orchestrator.stream_agent_chat(
            messages_input=messages,
            user_id=str(current_user.id),
            mode="chat"
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS
    )



# ── Authenticated Session Routes ─────────────────────────────────────────────

@router.post("/sessions", response_model=ChatSessionResponse)
@limiter.limit("60/minute")
def create_session(request: Request, session_data: ChatSessionCreate, current_user_data=Depends(get_current_user)):
    """Create a new chat session for the authenticated user."""
    current_user, token = current_user_data
    user_id_str = str(current_user.id)
    
    # Auto-ensure profile exists in profiles table before creating session (prevents chat_sessions_user_id_fkey 400 error)
    ensure_profile_exists(current_user, token)

    print(f"=== SESSION USER ID: {user_id_str} ===")

    try:
        db = get_authed_client(token)

        now_str = datetime.now(timezone.utc).isoformat()
        insert_payload = {
            "user_id": user_id_str,
            "title": session_data.title or "New Chat"
        }
        try:
            insert_payload["updated_at"] = now_str
            data = db.table("chat_sessions").insert(insert_payload).execute()
        except Exception as insert_err:
            print(f"Primary insert note in create_session: {insert_err}")
            if "updated_at" in insert_payload:
                del insert_payload["updated_at"]
            data = db.table("chat_sessions").insert(insert_payload).execute()

        if data.data and len(data.data) > 0:
            print(f"Successfully created session ID: {data.data[0].get('id')} for user ID: {user_id_str}")
            return data.data[0]
        else:
            fetched = db.table("chat_sessions").select("*").eq("user_id", user_id_str).order("created_at", desc=True).limit(1).execute()
            if fetched.data and len(fetched.data) > 0:
                return fetched.data[0]
            raise HTTPException(status_code=400, detail="Failed to retrieve created session.")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in create_session for user {user_id_str}: {e}")
        raise HTTPException(status_code=400, detail=f"Could not create session: {str(e)}")


@router.get("/sessions", response_model=List[ChatSessionResponse])
@limiter.limit("60/minute")
def get_sessions(
    request: Request,
    limit: int = 20,
    offset: int = 0,
    current_user_data=Depends(get_current_user)
):
    """
    Get chat sessions for authenticated user with lazy pagination.
    Supports limit (default 20, max 100) and offset query parameters.
    """
    current_user, token = current_user_data
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    try:
        db = get_authed_client(token)
        try:
            data = db.table("chat_sessions").select("*").eq(
                "user_id", str(current_user.id)
            ).order("updated_at", desc=True).range(offset, offset + limit - 1).execute()
        except Exception:
            data = db.table("chat_sessions").select("*").eq(
                "user_id", str(current_user.id)
            ).order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        return data.data or []
    except Exception as e:
        print(f"Error in get_sessions for user {getattr(current_user, 'id', None)}: {e}")
        raise HTTPException(status_code=400, detail="Could not load sessions.")


@router.get("/sessions/{session_id}/messages", response_model=List[ChatMessageResponse])
@limiter.limit("60/minute")
def get_messages(request: Request, session_id: str, current_user_data=Depends(get_current_user)):
    """Get messages for a specific session, explicitly limited to 500 records to handle large chats cleanly."""
    current_user, token = current_user_data
    try:
        db = get_authed_client(token)
        session = db.table("chat_sessions").select("id").eq(
            "id", session_id
        ).eq("user_id", str(current_user.id)).limit(1).execute()
        if not session.data:
            raise HTTPException(status_code=404, detail="Session not found")
        data = db.table("chat_messages").select("*").eq(
            "session_id", session_id
        ).order("created_at").limit(500).execute()
        return data.data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail="Could not load messages.")


@router.post("/sessions/{session_id}/messages", response_model=ChatMessageResponse)
@limiter.limit("30/minute")
def send_message(request: Request, session_id: str, message_data: ChatMessageCreate, current_user_data=Depends(get_current_user)):
    """Non-streaming authenticated message — auto-titles session on first message."""
    current_user, token = current_user_data
    try:
        db = get_authed_client(token)
        session = db.table("chat_sessions").select("id").eq(
            "id", session_id
        ).eq("user_id", str(current_user.id)).limit(1).execute()
        if not session.data:
            raise HTTPException(status_code=404, detail="Session not found")

        user_message = message_data.user_message
        assistant_message = "GROQ_API_KEY not set."

        # Auto-generate AI title if default
        _maybe_auto_title(db, session_id, user_message)

        if groq_client:
            try:
                history = db.table("chat_messages")\
                    .select("user_message, assistant_message")\
                    .eq("session_id", session_id)\
                    .order("created_at", desc=True)\
                    .limit(5).execute()

                context = _build_rag_context(db, str(current_user.id), message_data.mode, user_message)
                system_content = _build_system_content(message_data.mode, context)

                messages = [{"role": "system", "content": system_content}]
                for msg in reversed(history.data):
                    if msg.get("user_message"):
                        messages.append({"role": "user", "content": msg["user_message"]})
                    if msg.get("assistant_message"):
                        messages.append({"role": "assistant", "content": msg["assistant_message"]})
                messages.append({"role": "user", "content": user_message})

                chat_completion = call_groq_with_retry(
                    groq_client.chat.completions.create,
                    messages=messages, model="groq/compound-mini", max_tokens=1024,
                )
                assistant_message = chat_completion.choices[0].message.content
            except Exception as e:
                print(f"Groq API error: {e}")
                assistant_message = "Error generating response from AI. Please try again."

        data = db.table("chat_messages").insert({
            "session_id": session_id,
            "user_message": user_message,
            "assistant_message": assistant_message
        }).execute()
        return data.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail="Could not send message.")


@router.post("/sessions/{session_id}/messages/stream")
@limiter.limit("30/minute")
async def send_message_stream(request: Request, session_id: str, message_data: ChatMessageCreate, current_user_data=Depends(get_current_user)):
    """Streaming authenticated chat endpoint (SSE) — auto-titles session and saves full response to DB on completion."""
    current_user, token = current_user_data
    try:
        db = get_authed_client(token)
        session = db.table("chat_sessions").select("id").eq(
            "id", session_id
        ).eq("user_id", str(current_user.id)).limit(1).execute()
        if not session.data:
            raise HTTPException(status_code=404, detail="Session not found")

        user_message = message_data.user_message

        # Auto-generate AI title if default
        _maybe_auto_title(db, session_id, user_message)

        if not groq_client:
            async def no_key():
                yield f"data: {json.dumps({'text': 'GROQ_API_KEY not configured.'})}\\n\\n"
                yield "data: [DONE]\\n\\n"
            return StreamingResponse(no_key(), media_type="text/event-stream", headers=SSE_HEADERS)

        # Build conversation history
        history = db.table("chat_messages")\
            .select("user_message, assistant_message")\
            .eq("session_id", session_id)\
            .order("created_at", desc=True)\
            .limit(5).execute()

        messages = []
        for msg in reversed(history.data):
            if msg.get("user_message"):
                messages.append({"role": "user", "content": msg["user_message"]})
            if msg.get("assistant_message"):
                messages.append({"role": "assistant", "content": msg["assistant_message"]})
        messages.append({"role": "user", "content": user_message})

        async def generate_and_save():
            full_response = ""
            async for chunk in agent_orchestrator.stream_agent_chat(
                messages_input=messages,
                db=db,
                user_id=str(current_user.id),
                session_id=session_id,
                mode=message_data.mode or "chat"
            ):
                if chunk.startswith("data: ") and not chunk.startswith("data: [DONE]"):
                    try:
                        payload = json.loads(chunk[6:].strip())
                        if "text" in payload:
                            full_response += payload["text"]
                    except Exception:
                        pass
                yield chunk

            # Save complete response to DB (only if non-empty)
            if full_response.strip():
                try:
                    db.table("chat_messages").insert({
                        "session_id": session_id,
                        "user_message": user_message,
                        "assistant_message": full_response
                    }).execute()
                    try:
                        db.table("chat_sessions").update({
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }).eq("id", session_id).execute()
                    except Exception:
                        pass
                except Exception as db_err:
                    print(f"DB save error after stream: {db_err}")

        return StreamingResponse(generate_and_save(), media_type="text/event-stream", headers=SSE_HEADERS)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail="Could not start chat stream.")


# ── Shared helpers & RAG Caching ──────────────────────────────────────────────

def _build_rag_context(db, user_id: str, mode: str, user_message: str) -> str:
    """Retrieve relevant document chunks for RAG mode, with TTL memory caching for identical queries."""
    if mode != "rag":
        return ""
    
    # Check RAG query cache
    cache_key = f"rag:{user_id}:{user_message.strip().lower()}"
    cached_val = cache_service.get(cache_key)
    if cached_val is not None:
        return cached_val

    res_context = ""
    try:
        try:
            from app.services.vector_store import reranked_search_documents
            results = reranked_search_documents(user_id=user_id, query=user_message, top_k=4)
            if results:
                res_context = "\n\n".join(
                    f"From '{r['filename']}' ({r['file_type']}):\n{r['text']}"
                    for r in results
                )
        except Exception as chroma_err:
            print(f"ChromaDB RAG context failed: {chroma_err}")

        if not res_context:
            import os
            docsres = db.table("documents").select("filename").eq("user_id", user_id).limit(100).execute()
            filenames = [d["filename"] for d in docsres.data] if docsres.data else []
            chunks = []
            for fname in filenames:
                txt_path = os.path.join("uploads_temp", user_id, fname + ".txt")
                if os.path.exists(txt_path):
                    with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    for p in content.split("\n\n"):
                        p = p.strip()
                        if p:
                            chunks.append({"filename": fname, "text": p})
            query_words = {w.lower() for w in user_message.split() if len(w) > 2}
            scored = []
            for chunk in chunks:
                overlap = len(query_words & set(chunk["text"].lower().split()))
                if overlap > 0:
                    scored.append((overlap, chunk))
            scored.sort(key=lambda x: x[0], reverse=True)
            top = [c[1] for c in scored[:4]]
            res_context = "\n\n".join(f"From '{tc['filename']}':\n{tc['text']}" for tc in top)
    except Exception as e:
        print(f"RAG retrieval error: {e}")
        res_context = ""

    # Save to Redis / memory cache
    cache_service.set(cache_key, res_context, ttl_seconds=_RAG_CACHE_TTL)
    return res_context


def _build_system_content(mode: str, context: str) -> str:
    """Build system prompt based on active mode."""
    if mode == "rag" and context:
        return (
            f"{KHANNAX_SYSTEM_PROMPT}\n\n"
            "You also have Document Search (RAG) capabilities.\n"
            "Answer the user's question using ONLY the following retrieved context from their uploaded documents. "
            "If the context doesn't have what they need, say so naturally.\n\n"
            f"--- CONTEXT START ---\n{context}\n--- CONTEXT END ---"
        )
    if mode == "rag":
        return (
            f"{KHANNAX_SYSTEM_PROMPT}\n\n"
            "You have Document Search (RAG) capabilities. The user asked about their documents, "
            "but no matching text was found. Let them know naturally and offer help."
        )
    return KHANNAX_SYSTEM_PROMPT
