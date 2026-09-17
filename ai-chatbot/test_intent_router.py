from app.agent.intent_router import intent_router

tests = [
    ("Hi, how are you?",                                               "general_chat"),
    ("What is 25% of 80000",                                           "calculation"),
    ("Write a Python function to sort a list",                         "coding"),
    ("What does my uploaded PDF say about contracts?",                 "rag"),
    ("What is the latest news about AI today?",                        "web_search"),
    ("Analyze this image screenshot for me",                           "image_analysis"),
    ("Analyze my CSV dataset and show column stats",                   "document_analysis"),
    ("Give me a comprehensive deep dive on quantum computing history", "research"),
    ("syntax error in my code, TypeError on line 5",                   "coding"),
    ("ratio of 50 to 200",                                             "calculation"),
    ("search the web for python best practices 2024",                  "web_search"),
]

passed = 0
failed = 0
for msg, expected in tests:
    r = intent_router.classify(msg)
    ok = r.name == expected
    if ok:
        passed += 1
    else:
        failed += 1
    status = "OK  " if ok else "FAIL"
    print(f"{status} [{expected:<22}] got={r.name:<22} conf={r.confidence:.2f} | {msg[:50]}")

print(f"\nResults: {passed}/{passed+failed}")
