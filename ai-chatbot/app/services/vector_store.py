"""
ChromaDB Vector Store Service for RAG.

Provides semantic search over uploaded documents using ChromaDB with
sentence-transformers embeddings. Each user gets an isolated collection.

Pipeline: text → chunk → embed → store → query
"""
import os
import re
import hashlib
from typing import List, Dict, Optional, Tuple

# ── Lazy imports to avoid startup cost if not needed ─────────────────────────
_chroma_client = None
_embedding_fn = None

CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "chroma_data")
CHROMA_PERSIST_DIR = os.path.abspath(CHROMA_PERSIST_DIR)

# ── Chunking parameters ─────────────────────────────────────────────────────
CHUNK_SIZE = 500       # characters per chunk
CHUNK_OVERLAP = 80     # overlap between consecutive chunks
MIN_CHUNK_LENGTH = 30  # skip chunks shorter than this


def _get_chroma_client():
    """Lazy-initialize ChromaDB persistent client."""
    global _chroma_client
    if _chroma_client is None:
        import chromadb
        os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    return _chroma_client


def _get_embedding_function():
    """Lazy-initialize the sentence-transformers embedding function."""
    global _embedding_fn
    if _embedding_fn is None:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        _embedding_fn = SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
    return _embedding_fn


def _get_collection(user_id: str):
    """Get or create a per-user ChromaDB collection."""
    client = _get_chroma_client()
    ef = _get_embedding_function()
    # Collection names must be 3-63 chars, alphanumeric + underscores
    safe_name = "user_" + re.sub(r"[^a-zA-Z0-9_]", "_", user_id)[:55]
    return client.get_or_create_collection(
        name=safe_name,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"}
    )


# ── Text Chunking ───────────────────────────────────────────────────────────

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Split text into overlapping chunks.
    
    Tries to split on paragraph/sentence boundaries for cleaner chunks.
    Falls back to character-level splitting with overlap.
    """
    if not text or not text.strip():
        return []

    # Normalize whitespace
    text = text.strip()

    # First, try to split into paragraphs
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks = []
    current_chunk = ""

    for para in paragraphs:
        # If adding this paragraph would exceed chunk_size, finalize current chunk
        if current_chunk and len(current_chunk) + len(para) + 2 > chunk_size:
            if len(current_chunk) >= MIN_CHUNK_LENGTH:
                chunks.append(current_chunk)
            # Start new chunk with overlap from end of previous
            overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
            current_chunk = overlap_text + "\n\n" + para
        else:
            current_chunk = (current_chunk + "\n\n" + para).strip() if current_chunk else para

        # If single paragraph is larger than chunk_size, split it further
        while len(current_chunk) > chunk_size * 1.5:
            # Try to find a sentence boundary near chunk_size
            split_point = chunk_size
            for sep in [". ", "! ", "? ", "\n", "; ", ", "]:
                idx = current_chunk.rfind(sep, chunk_size // 2, chunk_size + 50)
                if idx != -1:
                    split_point = idx + len(sep)
                    break

            chunk_piece = current_chunk[:split_point].strip()
            if len(chunk_piece) >= MIN_CHUNK_LENGTH:
                chunks.append(chunk_piece)

            # Overlap into next piece
            overlap_start = max(0, split_point - overlap)
            current_chunk = current_chunk[overlap_start:].strip()

    # Don't forget the last chunk
    if current_chunk and len(current_chunk) >= MIN_CHUNK_LENGTH:
        chunks.append(current_chunk)

    return chunks


# ── Ingest (Upsert) ─────────────────────────────────────────────────────────

def ingest_document(
    user_id: str,
    filename: str,
    text_content: str,
    file_type: str = "unknown"
) -> int:
    """Chunk and ingest a document into the user's ChromaDB collection.
    
    Args:
        user_id: The user's ID for collection isolation.
        filename: Original filename of the document.
        text_content: Full extracted text content.
        file_type: Canonical file type (pdf, docx, etc.).
    
    Returns:
        Number of chunks ingested.
    """
    if not text_content or not text_content.strip():
        return 0

    collection = _get_collection(user_id)
    chunks = chunk_text(text_content)

    if not chunks:
        return 0

    # Delete any existing chunks for this filename (re-upload support)
    try:
        existing = collection.get(where={"filename": filename})
        if existing and existing["ids"]:
            collection.delete(ids=existing["ids"])
    except Exception:
        pass  # Collection might be empty or filter might not match

    # Prepare batch data
    ids = []
    documents = []
    metadatas = []

    for i, chunk in enumerate(chunks):
        # Deterministic ID based on user + filename + chunk index
        chunk_id = hashlib.md5(
            f"{user_id}:{filename}:{i}".encode()
        ).hexdigest()

        ids.append(chunk_id)
        documents.append(chunk)
        metadatas.append({
            "user_id": user_id,
            "filename": filename,
            "file_type": file_type,
            "chunk_index": i,
            "total_chunks": len(chunks),
        })


    # Upsert in batches (ChromaDB has a batch limit)
    batch_size = 100
    for start in range(0, len(ids), batch_size):
        end = start + batch_size
        collection.upsert(
            ids=ids[start:end],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
        )

    return len(chunks)


# ── Semantic Search ──────────────────────────────────────────────────────────

def search_documents(
    user_id: str,
    query: str,
    top_k: int = 5,
    filename_filter: Optional[str] = None
) -> List[Dict]:
    """Search for relevant document chunks using semantic similarity.
    
    Args:
        user_id: The user's ID.
        query: The search query.
        top_k: Number of top results to return.
        filename_filter: Optional filename to restrict search to.
    
    Returns:
        List of dicts with keys: text, filename, file_type, chunk_index, score
    """
    try:
        collection = _get_collection(user_id)

        # Check if collection has any documents
        if collection.count() == 0:
            return []

        if filename_filter:
            where_filter = {"$and": [{"user_id": user_id}, {"filename": filename_filter}]}
        else:
            where_filter = {"user_id": user_id}


        results = collection.query(
            query_texts=[query],
            n_results=min(top_k, collection.count()),
            where=where_filter,
        )

        if not results or not results["documents"] or not results["documents"][0]:
            return []

        output = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            distance = results["distances"][0][i] if results["distances"] else 1.0
            # ChromaDB cosine distance: 0 = identical, 2 = opposite
            # Convert to similarity score: 1 - (distance / 2)
            similarity = 1.0 - (distance / 2.0)

            output.append({
                "text": doc,
                "filename": meta.get("filename", "unknown"),
                "file_type": meta.get("file_type", "unknown"),
                "chunk_index": meta.get("chunk_index", 0),
                "total_chunks": meta.get("total_chunks", 1),
                "score": round(similarity, 4),
            })

        return output

    except Exception as e:
        print(f"ChromaDB search error: {e}")
        return []


# ── Delete Document ──────────────────────────────────────────────────────────

def delete_document(user_id: str, filename: str) -> bool:
    """Remove all chunks for a specific document from the user's collection."""
    try:
        collection = _get_collection(user_id)
        existing = collection.get(where={"filename": filename})
        if existing and existing["ids"]:
            collection.delete(ids=existing["ids"])
            return True
        return False
    except Exception as e:
        print(f"ChromaDB delete error: {e}")
        return False


# ── Hybrid Search (Vector + Keyword BM25 with RRF) ──────────────────────────


def hybrid_search_documents(
    user_id: str,
    query: str,
    top_k: int = 5,
    filename_filter: Optional[str] = None
) -> List[Dict]:
    """Perform Hybrid RAG Retrieval combining ChromaDB semantic search with Keyword BM25 ranking.
    Uses Reciprocal Rank Fusion (RRF) to merge search results.
    
    Falls back to standard ChromaDB vector search if hybrid processing fails.
    """
    try:
        # 1. Semantic Vector Search (ChromaDB)
        vector_results = search_documents(user_id=user_id, query=query, top_k=top_k * 2, filename_filter=filename_filter)
        
        # If collection is empty or no vector results, return empty
        if not vector_results:
            return []

        collection = _get_collection(user_id)
        if collection.count() == 0:
            return vector_results[:top_k]

        # 2. Fetch all document chunks from collection for keyword BM25 scoring
        if filename_filter:
            where_filter = {"$and": [{"user_id": user_id}, {"filename": filename_filter}]}
        else:
            where_filter = {"user_id": user_id}

        all_docs = collection.get(where=where_filter, include=["documents", "metadatas"])

        
        if not all_docs or not all_docs["documents"]:
            return vector_results[:top_k]

        # 3. Simple BM25 / Keyword Overlap Ranking
        query_words = [w.lower() for w in re.findall(r"\w+", query) if len(w) > 1]
        if not query_words:
            return vector_results[:top_k]

        keyword_scored = []
        for i, doc_text in enumerate(all_docs["documents"]):
            meta = all_docs["metadatas"][i] if all_docs["metadatas"] else {}
            doc_lower = doc_text.lower()
            doc_words = re.findall(r"\w+", doc_lower)
            doc_len = len(doc_words) or 1
            
            # Term Frequency & Exact Match Weighting
            tf = 0.0
            for qw in query_words:
                count = doc_words.count(qw)
                if count > 0:
                    tf += (count / (count + 1.2 * (0.25 + 0.75 * (doc_len / 200.0))))
            
            # Exact query phrase boost
            if query.lower() in doc_lower:
                tf += 2.0
                
            if tf > 0:
                keyword_scored.append({
                    "text": doc_text,
                    "filename": meta.get("filename", "unknown"),
                    "file_type": meta.get("file_type", "unknown"),
                    "chunk_index": meta.get("chunk_index", 0),
                    "score": tf
                })

        keyword_scored.sort(key=lambda x: x["score"], reverse=True)
        keyword_results = keyword_scored[:top_k * 2]

        # 4. Reciprocal Rank Fusion (RRF)
        # RRF Score = 1 / (60 + rank_vector) + 1 / (60 + rank_keyword)
        rrf_constant = 60
        fused_scores = {}  # key: (filename, chunk_index) -> item dict + rrf_score
        
        # Process vector ranks
        for rank, item in enumerate(vector_results):
            key = (item["filename"], item["chunk_index"])
            rrf_score = 1.0 / (rrf_constant + rank + 1)
            fused_scores[key] = {
                "item": item,
                "score": rrf_score
            }
            
        # Process keyword ranks
        for rank, item in enumerate(keyword_results):
            key = (item["filename"], item["chunk_index"])
            rrf_score = 1.0 / (rrf_constant + rank + 1)
            if key in fused_scores:
                fused_scores[key]["score"] += rrf_score
            else:
                fused_scores[key] = {
                    "item": item,
                    "score": rrf_score
                }

        # Sort by fused RRF score descending
        sorted_fused = sorted(fused_scores.values(), key=lambda x: x["score"], reverse=True)
        
        final_results = []
        for entry in sorted_fused[:top_k]:
            item = entry["item"]
            item["rrf_score"] = round(entry["score"], 6)
            final_results.append(item)

        return final_results if final_results else vector_results[:top_k]

    except Exception as e:
        print(f"Hybrid search fallback triggered: {e}")
        # Fallback to pure ChromaDB vector search
        return search_documents(user_id=user_id, query=query, top_k=top_k, filename_filter=filename_filter)


# ── Reranking Step (Second-Stage Cross-Encoder / Semantic Rescoring) ────────

_cross_encoder_model = None

def _get_cross_encoder():
    """Lazy-initialize Cross-Encoder model if sentence-transformers is available."""
    global _cross_encoder_model
    if _cross_encoder_model is None:
        try:
            from sentence_transformers import CrossEncoder
            _cross_encoder_model = CrossEncoder("cross-encoder/ms-marco-TinyBERT-L-2-v2", max_length=512)
        except Exception as e:
            print(f"CrossEncoder initialization info: {e}")
            _cross_encoder_model = False
    return _cross_encoder_model if _cross_encoder_model is not False else None


def rerank_documents(query: str, candidates: List[Dict], top_k: int = 5) -> List[Dict]:
    """Rerank candidate document chunks using a Cross-Encoder or semantic similarity.
    
    If cross-encoder fails or is unavailable, falls back to returning candidates as-is.
    """
    if not candidates:
        return []

    try:
        model = _get_cross_encoder()
        if model is not None:
            pairs = [[query, c["text"]] for c in candidates]
            scores = model.predict(pairs)
            for i, score in enumerate(scores):
                candidates[i]["rerank_score"] = round(float(score), 4)
            reranked = sorted(candidates, key=lambda x: x.get("rerank_score", 0), reverse=True)
            return reranked[:top_k]
        
        # Fallback ranking: Term overlap & sequence similarity
        q_words = set(re.findall(r"\w+", query.lower()))
        for c in candidates:
            c_text_lower = c["text"].lower()
            overlap = sum(1 for w in q_words if w in c_text_lower)
            c["rerank_score"] = round(overlap / (len(q_words) or 1), 4)
        reranked = sorted(candidates, key=lambda x: x.get("rerank_score", 0), reverse=True)
        return reranked[:top_k]

    except Exception as e:
        print(f"Reranking warning: {e}, falling back to candidate order")
        return candidates[:top_k]


def reranked_search_documents(
    user_id: str,
    query: str,
    top_k: int = 5,
    candidate_k: int = 15,
    filename_filter: Optional[str] = None
) -> List[Dict]:
    """Execute candidate retrieval (ChromaDB hybrid) followed by second-stage reranking.
    
    Flow: Query -> ChromaDB Hybrid Candidates (15) -> Cross-Encoder Reranker -> Top k (5) -> LLM.
    Falls back gracefully to ChromaDB vector search if any step fails.
    """
    try:
        # Step 1: Retrieve candidate pool (default top 15)
        candidates = hybrid_search_documents(
            user_id=user_id,
            query=query,
            top_k=candidate_k,
            filename_filter=filename_filter
        )
        
        if not candidates:
            return []

        # Step 2: Second-stage reranking
        return rerank_documents(query=query, candidates=candidates, top_k=top_k)

    except Exception as e:
        print(f"Reranked search failed: {e}, falling back to vector search")
        return search_documents(user_id=user_id, query=query, top_k=top_k, filename_filter=filename_filter)


# ── Multi-Document Helpers ───────────────────────────────────────────────────

def get_user_documents(user_id: str) -> List[str]:
    """Retrieve unique filenames uploaded by the user in ChromaDB."""
    try:
        collection = _get_collection(user_id)
        if collection.count() == 0:
            return []
        data = collection.get(where={"user_id": user_id}, include=["metadatas"])
        if not data or not data.get("metadatas"):
            return []
        filenames = sorted(list({meta["filename"] for meta in data["metadatas"] if meta and "filename" in meta}))
        return filenames
    except Exception as e:
        print(f"Error fetching user document names: {e}")
        return []


def get_multi_document_context(
    user_id: str,
    filenames: Optional[List[str]] = None,
    max_chunks_per_doc: int = 8
) -> Dict[str, List[str]]:
    """Retrieve document chunks grouped by filename for multi-doc analysis/comparison."""
    try:
        collection = _get_collection(user_id)
        if collection.count() == 0:
            return {}

        where_filter = {"user_id": user_id}
        data = collection.get(where=where_filter, include=["documents", "metadatas"])
        if not data or not data.get("documents"):
            return {}

        grouped: Dict[str, List[Tuple[int, str]]] = {}
        for i, doc_text in enumerate(data["documents"]):
            meta = data["metadatas"][i] if data["metadatas"] else {}
            fname = meta.get("filename", "unknown")
            if filenames and fname not in filenames:
                continue
            chunk_idx = meta.get("chunk_index", i)
            if fname not in grouped:
                grouped[fname] = []
            grouped[fname].append((chunk_idx, doc_text))

        result: Dict[str, List[str]] = {}
        for fname, chunks in grouped.items():
            chunks.sort(key=lambda x: x[0])  # Preserve chunk order
            result[fname] = [c[1] for c in chunks[:max_chunks_per_doc]]

        return result
    except Exception as e:
        print(f"Error getting multi-document context: {e}")
        return {}



