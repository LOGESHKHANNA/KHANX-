import sys
import os
import subprocess
import tempfile
from app.agent.sandbox import SAFE_RUNNER_SCRIPT

code = """
import statistics
data = [10.5, 20.0, 30.5, 40.0, 50.0]
mean_val = statistics.mean(data)
stdev_val = statistics.stdev(data)
print(f"Mean: {mean_val}, Stdev: {stdev_val:.2f}")
"""
temp_dir = tempfile.mkdtemp(prefix="khanx_sandbox_debug_")
code_file_path = os.path.join(temp_dir, "script.py")
runner_file_path = os.path.join(temp_dir, "runner.py")

with open(code_file_path, "w", encoding="utf-8") as f:
    f.write(code)

with open(runner_file_path, "w", encoding="utf-8") as f:
    f.write(SAFE_RUNNER_SCRIPT)

print("Starting subprocess...")
proc = subprocess.Popen(
    [sys.executable, runner_file_path, code_file_path],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    cwd=temp_dir,
    text=True
)
print("Waiting for subprocess...")
stdout, stderr = proc.communicate() # no timeout!
print("Process exit code:", proc.returncode)
print("STDOUT:", stdout)
print("STDERR:", stderr)
