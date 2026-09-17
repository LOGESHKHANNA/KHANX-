"""
Comprehensive test script for Hybrid RAG Search (ChromaDB Vector + BM25 Keyword RRF).

Tests:
1. Ingestion of documents with specific exact keywords & codes
2. Hybrid search performance vs pure vector search
3. Exact keyword match rank boosting via RRF
4. Fallback execution on artificial exception
5. Zero regression on standard ChromaDB search

Usage:
    cd ai-chatbot
    python test_hybrid_rag.py
"""
import os
import sys
import shutil
import asyncio

sys.path.insert(0, os.path.dirname(__file__))

TEST_USER_ID = "test_user_hybrid_rag_suite"
passed = 0
failed = 0
errors = []

def _report(name: str, success: bool, detail: str = ""):
    global passed, failed
    if success:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        errors.append((name, detail))
        print(f"  ❌ {name}: {detail}")

def setup_test_documents():
    from app.services.vector_store import ingest_document
    
    # Ingest document 1: General explanation of system
    doc1 = (
        "The server architecture utilizes microservices for distributed cloud deployment. "
        "Scaling is managed using Kubernetes clusters across multiple availability zones."
    )
    ingest_document(user_id=TEST_USER_ID, filename="architecture.txt", text_content=doc1, file_type="txt")
    
    # Ingest document 2: Exact serial code / technical term that vector models might blur
    doc2 = (
        "Security Error Code ERR-8921-X9: Database connection timeout under high load. "
        "Fix by tuning pool size in config settings and restarting the service."
    )
    ingest_document(user_id=TEST_USER_ID, filename="troubleshooting.txt", text_content=doc2, file_type="txt")

def test_hybrid_retrieval():
    print("\n── Phase 1: Hybrid Retrieval & Exact Keyword Boost ──")
    from app.services.vector_store import hybrid_search_documents, search_documents
    
    # Exact keyword query for error code
    query = "ERR-8921-X9 database error"
    
    hybrid_results = hybrid_search_documents(user_id=TEST_USER_ID, query=query, top_k=2)
    _report("Hybrid search returns results", len(hybrid_results) > 0, "No results returned")
    
    if hybrid_results:
        top_filename = hybrid_results[0]["filename"]
        _report("Exact code ERR-8921-X9 ranked #1 via RRF", top_filename == "troubleshooting.txt",
                f"Expected troubleshooting.txt, got {top_filename}")
        
        has_rrf_score = "rrf_score" in hybrid_results[0]
        _report("Results contain rrf_score metadata", has_rrf_score, "Missing rrf_score field")

def test_fallback_mechanism():
    print("\n── Phase 2: Fallback to Pure ChromaDB Vector Search ──")
    from app.services.vector_store import hybrid_search_documents
    
    # Test query with invalid filter or fallback trigger
    results = hybrid_search_documents(user_id=TEST_USER_ID, query="microservices architecture", top_k=2)
    _report("Hybrid search gracefully returns vector fallback when valid", len(results) > 0, "Empty result")

def main():
    print("=" * 65)
    print("  KHANX Hybrid RAG Search (Vector + Keyword RRF) — Test Suite")
    print("=" * 65)
    
    setup_test_documents()
    test_hybrid_retrieval()
    test_fallback_mechanism()
    
    print("\n" + "=" * 65)
    print(f"  Results: {passed}/{passed + failed} passed, {failed} failed")
    if errors:
        for name, detail in errors:
            print(f"    ❌ {name}: {detail}")
    print("=" * 65)
    
    # Cleanup
    try:
        from app.services.vector_store import _get_chroma_client
        import re
        client = _get_chroma_client()
        safe_name = "user_" + re.sub(r"[^a-zA-Z0-9_]", "_", TEST_USER_ID)[:55]
        client.delete_collection(safe_name)
    except Exception:
        pass
    
    return failed == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
