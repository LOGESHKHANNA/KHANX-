from fastapi import APIRouter, File, UploadFile, HTTPException, Depends, BackgroundTasks, Request
from typing import List
from app.schemas.document import DocumentResponse
from app.services.supabase_client import get_authed_client
from app.services.text_extractor import extract_text, is_supported, get_supported_extensions_str
from app.services import vector_store
from app.api.deps import get_current_user
from app.core.config import settings
from app.core.limiter import limiter
import uuid
import os

router = APIRouter()

# Temp directory for processing text extraction before cloud storage / cleanup
TEMP_DIR = "uploads_temp"
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB
os.makedirs(TEMP_DIR, exist_ok=True)

@router.post("/upload", response_model=DocumentResponse)
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user_data = Depends(get_current_user)
):
    """
    Upload a document.
    File is stored in Supabase Cloud Storage ('documents' bucket) scoped by user ID.
    Text is extracted and ingested into ChromaDB for instant vector search RAG.
    """
    current_user, token = current_user_data
    user_id_str = str(current_user.id)
    db = get_authed_client(token)

    # Clean file name to prevent traversal
    safe_filename = os.path.basename(file.filename)

    # ── Validate file type ────────────────────────────────────────────────
    if not is_supported(safe_filename):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Supported formats: {get_supported_extensions_str()}"
        )

    # Create temporary local file for text extraction
    user_temp_dir = os.path.join(TEMP_DIR, user_id_str)
    os.makedirs(user_temp_dir, exist_ok=True)
    temp_file_path = os.path.join(user_temp_dir, f"{uuid.uuid4().hex[:8]}_{safe_filename}")

    file_size = 0
    file_bytes = bytearray()
    try:
        # Save to temp file and buffer in memory for cloud upload
        with open(temp_file_path, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                file_size += len(chunk)
                if file_size > MAX_FILE_SIZE:
                    f.close()
                    if os.path.exists(temp_file_path):
                        os.remove(temp_file_path)
                    raise HTTPException(
                        status_code=400,
                        detail="File size exceeds maximum allowed limit (25 MB)."
                    )
                f.write(chunk)
                file_bytes.extend(chunk)

        file_ext_type = os.path.splitext(safe_filename)[1][1:].lower() or "unknown"

        # ── 1. Cloud Storage Upload to Supabase Storage ───────────────────
        storage_bucket = settings.SUPABASE_STORAGE_BUCKET or "documents"
        storage_path = f"{user_id_str}/{safe_filename}"
        cloud_upload_success = False

        try:
            # Upload binary buffer directly to Supabase Storage bucket
            upload_res = db.storage.from_(storage_bucket).upload(
                path=storage_path,
                file=bytes(file_bytes),
                file_options={"upsert": "true"}
            )
            cloud_upload_success = True
            print(f"Supabase Storage: Uploaded '{storage_path}' to bucket '{storage_bucket}'")
        except Exception as storage_err:
            print(f"Supabase Storage warning (bucket '{storage_bucket}'): {storage_err}")
            # Non-blocking fallback: process locally if bucket is not created yet

        # ── 2. Text Extraction & Vector Store Ingestion ───────────────────
        text_content = ""
        ftype = file_ext_type
        try:
            text_content, ftype = await extract_text(temp_file_path, safe_filename)
        except Exception as extract_err:
            print(f"Text extraction warning for {safe_filename}: {extract_err}")
            text_content = f"Error: Could not extract text from {safe_filename}."

        try:
            if text_content and not text_content.startswith("Error:"):
                chunks_ingested = vector_store.ingest_document(
                    user_id=user_id_str,
                    filename=safe_filename,
                    text_content=text_content,
                    file_type=ftype,
                )
                print(f"ChromaDB: Ingested {chunks_ingested} chunks for '{safe_filename}'")
        except Exception as chroma_err:
            print(f"ChromaDB ingestion warning for {safe_filename}: {chroma_err}")

        # ── 3. Insert metadata into Supabase 'documents' table ─────────────
        insert_payload = {
            "user_id": user_id_str,
            "filename": safe_filename,
        }

        try:
            insert_payload["file_type"] = ftype or file_ext_type
            insert_payload["file_size"] = file_size
            insert_payload["storage_path"] = storage_path if cloud_upload_success else None
            data = db.table("documents").insert(insert_payload).execute()
        except Exception:
            insert_payload_basic = {
                "user_id": user_id_str,
                "filename": safe_filename,
            }
            data = db.table("documents").insert(insert_payload_basic).execute()

        return data.data[0]

    finally:
        # Clean up temporary local file
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception:
                pass


@router.get("", response_model=List[DocumentResponse])
@router.get("/", response_model=List[DocumentResponse])
@limiter.limit("30/minute")
def get_documents(request: Request, current_user_data = Depends(get_current_user)):
    """Fetch all document records for the authenticated user."""
    current_user, token = current_user_data
    try:
        db = get_authed_client(token)
        data = db.table("documents").select("*").eq("user_id", str(current_user.id)).order("uploaded_at", desc=True).limit(200).execute()
        return data.data
    except Exception as e:
        raise HTTPException(status_code=400, detail="Could not load documents.")


@router.get("/supported-formats")
def get_supported_formats():
    """Returns the list of supported document & image file formats."""
    return {
        "supported_extensions": sorted(list(
            {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".txt", ".md", ".csv", ".tsv", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
        )),
        "description": "Upload any of these formats for AI-powered document search (RAG) or Image Understanding."
    }
