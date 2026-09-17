import os
from typing import Any, Dict, Optional
from app.agent.tools.base import BaseTool

class KnowledgeBaseTool(BaseTool):
    """Tool that searches uploaded documents using ChromaDB semantic search.
    Falls back to keyword matching if ChromaDB is unavailable."""
    name = "search_knowledge_base"
    description = "Search through user's uploaded documents (PDF, DOCX, PPTX, TXT, CSV, XLSX) to find relevant information and context."
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Keywords or question to search within the uploaded documents."
            }
        },
        "required": ["query"]
    }

    async def execute(self, query: str, db: Optional[Any] = None, user_id: Optional[str] = None, **kwargs: Any) -> str:
        """Search uploaded user documents — ChromaDB semantic search with keyword fallback."""
        if not user_id or not db:
            return "No document context available (User not authenticated or database context missing)."

        try:
            # ── Primary: ChromaDB Candidate Retrieval + Reranking Step ────────
            try:
                from app.services.vector_store import reranked_search_documents
                results = reranked_search_documents(user_id=user_id, query=query, top_k=5)
                if results:
                    formatted = []
                    for r in results:
                        score_str = f"rerank_score: {r['rerank_score']}" if "rerank_score" in r else f"relevance: {r.get('score', 0):.0%}"
                        chunk_str = f" [Chunk {r['chunk_index'] + 1}/{r.get('total_chunks', 1)}]" if "chunk_index" in r else ""
                        header = f"Source Document: '{r['filename']}' ({r['file_type']}){chunk_str} [{score_str}]:"
                        formatted.append(f"{header}\n{r['text']}")
                    return "\n\n---\n\n".join(formatted)
            except Exception as chroma_err:
                print(f"Reranked search failed, falling back to keyword search: {chroma_err}")



            # ── Fallback: Keyword Overlap Search on .txt sidecar files ──
            docsres = db.table("documents").select("filename").eq("user_id", user_id).execute()
            filenames = [d["filename"] for d in docsres.data] if docsres.data else []

            if not filenames:
                return "No documents have been uploaded yet."

            chunks = []
            for fname in filenames:
                txt_path = os.path.join("uploads", user_id, fname + ".txt")
                if os.path.exists(txt_path):
                    with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    for p in content.split("\n\n"):
                        p = p.strip()
                        if p:
                            chunks.append({"filename": fname, "text": p})

            if not chunks:
                return "Uploaded documents do not contain readable text."

            query_words = {w.lower() for w in query.split() if len(w) > 2}
            scored = []
            for chunk in chunks:
                overlap = len(query_words & set(chunk["text"].lower().split()))
                if overlap > 0:
                    scored.append((overlap, chunk))

            if not scored:
                return f"No relevant content found in uploaded documents matching query '{query}'."

            scored.sort(key=lambda x: x[0], reverse=True)
            top = [c[1] for c in scored[:5]]
            return "\n\n".join(f"From '{tc['filename']}':\n{tc['text']}" for tc in top)

        except Exception as e:
            return f"Error searching knowledge base: {str(e)}"
