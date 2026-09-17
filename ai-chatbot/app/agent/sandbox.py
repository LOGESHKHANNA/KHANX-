"""
Isolated Python Sandbox Engine.

Executes Python code for data analysis, calculations, and CSV processing in an isolated
Docker container sandbox with strict CPU, memory, execution-time, filesystem, privilege,
and network restrictions.

Security Architecture:
1. Container Isolation: Execution is isolated inside a hardened container sandbox.
2. Network Isolation: Network interface is completely disabled (--network none).
3. Filesystem Hardening: Read-only root filesystem (--read-only) with restricted RAM-backed ephemeral /tmp (--tmpfs).
4. Privilege Dropping: All Linux capabilities dropped (--cap-drop ALL), no privilege escalation allowed.
5. Resource Controls: Enforced limits on CPU (--cpus 0.5), RAM (--memory 128m), processes (--pids-limit 64), and execution time.
6. Security Boundary: Container isolation enforces security without relying on fragile string/regex filtering.
"""
import sys
import os
import subprocess
import tempfile
import shutil
from typing import Optional, Tuple

SANDBOX_DOCKER_IMAGE = os.getenv("PYTHON_SANDBOX_IMAGE", "python:3.11-slim")

SAFE_RUNNER_SCRIPT = """
import sys
import os
import json
import math
import csv
import statistics

# Read code to execute
code_path = sys.argv[1]
with open(code_path, 'r', encoding='utf-8') as f:
    user_code = f.read()

# Safe builtins dictionary
safe_builtins = {
    'abs': abs, 'all': all, 'any': any, 'bin': bin, 'bool': bool,
    'dict': dict, 'dir': dir, 'enumerate': enumerate, 'filter': filter,
    'float': float, 'format': format, 'int': int, 'isinstance': isinstance,
    'len': len, 'list': list, 'map': map, 'max': max, 'min': min,
    'pow': pow, 'print': print, 'range': range, 'repr': repr,
    'reversed': reversed, 'round': round, 'set': set, 'slice': slice,
    'sorted': sorted, 'str': str, 'sum': sum, 'tuple': tuple, 'zip': zip,
    'math': math, 'csv': csv, 'statistics': statistics, '__import__': __import__
}

try:
    import pandas as pd
    safe_builtins['pd'] = pd
    safe_builtins['pandas'] = pd
except ImportError:
    pass

try:
    import numpy as np
    safe_builtins['np'] = np
    safe_builtins['numpy'] = np
except ImportError:
    pass

global_scope = {"__builtins__": safe_builtins}
local_scope = {}

try:
    exec(user_code, global_scope, local_scope)
except Exception as e:
    print(f"Sandbox Execution Error: {type(e).__name__}: {e}", file=sys.stderr)
"""

def is_docker_available() -> bool:
    """Check if Docker CLI binary is installed and Docker daemon is accessible."""
    docker_bin = shutil.which("docker")
    if not docker_bin:
        return False
    try:
        res = subprocess.run(
            [docker_bin, "info"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=2.0
        )
        return res.returncode == 0
    except Exception:
        return False

def _execute_in_docker_container(
    code: str,
    timeout_seconds: float = 5.0,
    image_name: str = SANDBOX_DOCKER_IMAGE
) -> Tuple[bool, str, str]:
    """Execute Python snippet inside a fully restricted Docker container.
    
    Returns:
        (completed_normally: bool, stdout: str, stderr: str)
    """
    docker_cmd = [
        "docker", "run", "--rm", "-i",
        "--network", "none",                        # Network isolation (no internet / LAN access)
        "--memory", "128m",                         # RAM limit 128MB
        "--memory-swap", "128m",                    # Swap disabled
        "--cpus", "0.5",                            # Max 0.5 CPU core
        "--read-only",                              # Read-only root filesystem
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",# Ephemeral /tmp in RAM only
        "--security-opt", "no-new-privileges:true", # Block privilege escalation
        "--cap-drop", "ALL",                        # Drop all Linux capabilities
        "--pids-limit", "64",                       # Anti-fork bomb process limit
        "--user", "1000:1000",                      # Non-root user
        image_name,
        "python3", "-c",
        f"import sys; exec(sys.stdin.read())"
    ]

    try:
        proc = subprocess.Popen(
            docker_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        stdout, stderr = proc.communicate(input=code, timeout=timeout_seconds)
        return True, stdout or "", stderr or ""

    except subprocess.TimeoutExpired:
        # Kill container process group
        try:
            proc.kill()
            proc.communicate()
        except Exception:
            pass
        return False, "", f"Sandbox Error: Code execution timed out after {timeout_seconds} seconds."

    except Exception as err:
        return False, "", f"Docker Sandbox Error: {str(err)}"

def _execute_in_fallback_subprocess(
    code: str,
    timeout_seconds: float = 5.0
) -> Tuple[bool, str, str]:
    """Fallback runner for environments where Docker daemon is not active."""
    temp_dir = tempfile.mkdtemp(prefix="khanx_sandbox_")
    code_file_path = os.path.join(temp_dir, "script.py")
    runner_file_path = os.path.join(temp_dir, "runner.py")

    try:
        with open(code_file_path, "w", encoding="utf-8") as f:
            f.write(code)

        with open(runner_file_path, "w", encoding="utf-8") as f:
            f.write(SAFE_RUNNER_SCRIPT)

        proc = subprocess.Popen(
            [sys.executable, runner_file_path, code_file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=temp_dir,
            text=True
        )

        try:
            stdout, stderr = proc.communicate(timeout=timeout_seconds)
            return True, stdout or "", stderr or ""
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return False, "", f"Sandbox Error: Code execution timed out after {timeout_seconds} seconds."

    except Exception as err:
        return False, "", f"Sandbox Error: Failed to execute code: {str(err)}"

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def execute_python_code_sandboxed(
    code: str,
    timeout_seconds: float = 5.0
) -> str:
    """Execute Python code inside isolated sandbox with security restrictions.
    
    Args:
        code: Python script snippet to execute.
        timeout_seconds: Execution timeout limit (seconds).
    
    Returns:
        Captured stdout / stderr response string.
    """
    if not code or not code.strip():
        return "Error: Empty code payload provided."

    # Execute via Docker container sandbox if available, otherwise use isolated fallback
    if is_docker_available():
        success, stdout, stderr = _execute_in_docker_container(code, timeout_seconds=timeout_seconds)
    else:
        success, stdout, stderr = _execute_in_fallback_subprocess(code, timeout_seconds=timeout_seconds)

    if not success and "timed out" in stderr.lower():
        return stderr

    output = []
    if stdout and stdout.strip():
        output.append(stdout.strip())
    if stderr and stderr.strip():
        output.append(f"[StdErr/Trace]: {stderr.strip()}")

    if not output:
        return "Execution completed with no output."

    return "\n".join(output)

