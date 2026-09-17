"""
Comprehensive test script for KHANX Private Per-User Knowledge Space Isolation.

Tests:
1. Dual-tenant document ingestion under distinct user IDs (User_Alpha, User_Beta)
2. Collection-level & metadata-level isolation verification
3. Query scoping (User_Alpha gets Document A only, User_Beta gets Document B only)
4. Cross-tenant privacy enforcement (User_Beta asking for User_Alpha's document returns 0 results)

Usage:
    cd ai-chatbot
    python test_private_knowledge_space.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

USER_ALPHA = "usr_alpha_991"
USER_BETA = "usr_beta_882"

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

def setup_tenant_documents():
    from app.services.vector_store import ingest_document
    
    # User Alpha confidential document
    doc_alpha = "CONFIDENTIAL PROJECT ALPHA: High-energy particle containment protocol v4.2."
    ingest_document(user_id=USER_ALPHA, filename="alpha_secret.txt", text_content=doc_alpha, file_type="txt")
    
    # User Beta confidential document
    doc_beta = "CONFIDENTIAL PROJECT BETA: Deep sea sonar propulsion telemetry logs."
    ingest_document(user_id=USER_BETA, filename="beta_secret.txt", text_content=doc_beta, file_type="txt")

def test_tenant_isolation():
    print("\n── Phase 1: Knowledge Space Isolation Checks ──")
    from app.services.vector_store import reranked_search_documents
    
    # User Alpha query
    alpha_res = reranked_search_documents(user_id=USER_ALPHA, query="containment protocol", top_k=5)
    _report("User Alpha receives Alpha document", len(alpha_res) > 0 and alpha_res[0]["filename"] == "alpha_secret.txt", f"Got: {alpha_res}")
    
    # User Beta query
    beta_res = reranked_search_documents(user_id=USER_BETA, query="sonar propulsion telemetry", top_k=5)
    _report("User Beta receives Beta document", len(beta_res) > 0 and beta_res[0]["filename"] == "beta_secret.txt", f"Got: {beta_res}")

def test_cross_tenant_intrusion():
    print("\n── Phase 2: Cross-Tenant Intrusion Protection ──")
    from app.services.vector_store import reranked_search_documents
    
    # User Beta tries to query User Alpha's secret keyword "containment protocol"
    intrusion_res = reranked_search_documents(user_id=USER_BETA, query="containment protocol", top_k=5)
    _report("User Beta blocked from User Alpha's knowledge space", len(intrusion_res) == 0, f"Leaked results: {intrusion_res}")

def main():
    print("=" * 65)
    print("  KHANX Private Per-User Knowledge Space Isolation — Test Suite")
    print("=" * 65)
    
    setup_tenant_documents()
    test_tenant_isolation()
    test_cross_tenant_intrusion()
    
    print("\n" + "=" * 65)
    print(f"  Results: {passed}/{passed + failed} passed, {failed} failed")
    if errors:
        for name, detail in errors:
            print(f"    ❌ {name}: {detail}")
    print("=" * 65)
    
    # Cleanup collections
    try:
        from app.services.vector_store import _get_chroma_client
        import re
        client = _get_chroma_client()
        client.delete_collection("user_" + re.sub(r"[^a-zA-Z0-9_]", "_", USER_ALPHA)[:55])
        client.delete_collection("user_" + re.sub(r"[^a-zA-Z0-9_]", "_", USER_BETA)[:55])
    except Exception:
        pass
    
    return failed == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
