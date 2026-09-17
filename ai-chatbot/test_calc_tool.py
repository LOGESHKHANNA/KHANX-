"""
Comprehensive test script for KHANX Safe Calculator Tool.

Tests:
1. Arithmetic (+, -, *, /, **, %)
2. Percentages (e.g. 25% of 80,000)
3. Ratios (e.g. ratio of 50 to 200)
4. Averages (e.g. average of 10, 20, 30, 40)
5. Zero unsafe arbitrary code execution security protection

Usage:
    cd ai-chatbot
    python test_calc_tool.py
"""
import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(__file__))

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

async def test_calculator():
    print("\n── Phase 1: Mathematical Calculations ──")
    from app.agent.tools.calc_tool import CalculatorTool
    tool = CalculatorTool()
    
    # 1. Arithmetic
    res1 = await tool.execute("(15 * 4) + 120")
    _report("Arithmetic (15 * 4 + 120)", "180" in res1, f"Got: {res1}")
    
    # 2. Percentage
    res2 = await tool.execute("25% of 80,000")
    _report("Percentage (25% of 80,000)", "20000" in res2, f"Got: {res2}")
    
    # 3. Ratio
    res3 = await tool.execute("ratio of 50 to 200")
    _report("Ratio (ratio of 50 to 200)", "1:4" in res3 or "0.25" in res3, f"Got: {res3}")
    
    # 4. Average
    res4 = await tool.execute("average of 10, 20, 30, 40")
    _report("Average (average of 10, 20, 30, 40)", "25" in res4, f"Got: {res4}")
    
    # 5. Security: Unsafe Code Execution Attempt
    res5 = await tool.execute("__import__('os').system('dir')")
    _report("Unsafe execution attempt blocked safely", "Error" in res5 or "not allowed" in res5, f"Got: {res5}")

def main():
    print("=" * 65)
    print("  KHANX Safe Calculator Tool — Test Suite")
    print("=" * 65)
    
    asyncio.run(test_calculator())
    
    print("\n" + "=" * 65)
    print(f"  Results: {passed}/{passed + failed} passed, {failed} failed")
    if errors:
        for name, detail in errors:
            print(f"    ❌ {name}: {detail}")
    print("=" * 65)
    
    return failed == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
