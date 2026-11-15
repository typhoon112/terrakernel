"""Sandboxed execution of agent-written Python.

Each call runs in a fresh subprocess with:
- the agent's workspace copy as the working directory;
- an empty environment (no credentials, no proxy settings) except PATH/HOME/PYTHONPATH;
- no network (a new user + network namespace via ``unshare`` when available);
- CPU-time, address-space and output limits, and a wall-clock timeout.

The home directory is not hidden; agent runs are only started locally by the operator.
"""

from __future__ import annotations

import os
import resource
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

OUTPUT_LIMIT = 12_000
_UNSHARE: bool | None = None


def _unshare_available() -> bool:
    global _UNSHARE
    if _UNSHARE is None:
        exe = shutil.which("unshare")
        if not exe:
            _UNSHARE = False
        else:
            try:
                r = subprocess.run([exe, "--user", "--map-root-user", "--net", "true"], capture_output=True, timeout=10)
                _UNSHARE = r.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                _UNSHARE = False
    return _UNSHARE


def _limits(cpu_seconds: int, memory_mb: int):
    def apply() -> None:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        mem = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        resource.setrlimit(resource.RLIMIT_FSIZE, (200 * 1024 * 1024, 200 * 1024 * 1024))
        os.setsid()

    return apply


def run_python(code: str, workspace: Path, timeout: int = 90, cpu_seconds: int = 120, memory_mb: int = 3072) -> dict:
    """Run ``code`` in the sandbox and return {"exit_code", "output", "timed_out", "network_isolated"}."""
    workspace = Path(workspace)
    with tempfile.NamedTemporaryFile("w", suffix=".py", dir=workspace, prefix=".agent_", delete=False) as f:
        f.write(code)
        script = Path(f.name)
    env = {"PATH": "/usr/bin:/bin", "HOME": str(workspace), "PYTHONDONTWRITEBYTECODE": "1", "MPLBACKEND": "Agg",
           "PYTHONIOENCODING": "utf-8", "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
    cmd = [sys.executable, "-I", script.name] if not (workspace / "tools").exists() else [sys.executable, script.name]
    if (workspace / "tools").exists():
        env["PYTHONPATH"] = str(workspace / "tools")
    isolated = _unshare_available()
    if isolated:
        cmd = ["unshare", "--user", "--map-root-user", "--net", *cmd]
    try:
        proc = subprocess.run(cmd, cwd=workspace, env=env, capture_output=True, text=True, timeout=timeout,
                              preexec_fn=_limits(cpu_seconds, memory_mb))
        out = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr else "")
        result = {"exit_code": proc.returncode, "timed_out": False}
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        out += f"\n[timed out after {timeout}s]"
        result = {"exit_code": -1, "timed_out": True}
    finally:
        script.unlink(missing_ok=True)
    if len(out) > OUTPUT_LIMIT:
        out = out[: OUTPUT_LIMIT // 2] + f"\n... [{len(out) - OUTPUT_LIMIT} characters omitted] ...\n" + out[-OUTPUT_LIMIT // 2:]
    result.update(output=out, network_isolated=isolated)
    return result
