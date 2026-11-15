"""A small, transparent tool-use agent used to test research repositories.

It is deliberately minimal and identical across experimental settings: the same model,
system prompt, tools and limits; only the workspace contents differ. Every step is
recorded in a trace so a run can be inspected or replayed.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pdfplumber
from pydantic import BaseModel, Field, ValidationError

from terrakernel.agent.sandbox import run_python
from terrakernel.llm.client import LLMClient, LLMError, estimate_cost
from terrakernel.util import now_iso

MAX_READ_CHARS = 20_000
HIDDEN = {".terrakernel", "__pycache__", ".pytest_cache", ".venv", ".git"}


class ReportedValue(BaseModel):
    name: str
    value: float
    unit: str = ""


class Answer(BaseModel):
    values: list[ReportedValue]
    summary: str = Field(description="What was done and the main result")
    transformations: list[str] = Field(default_factory=list, description="Unit conversions, alignment, sample selection")
    open_issues: list[str] = Field(default_factory=list, description="What the materials leave unresolved")
    citations: list[str] = Field(default_factory=list, description="Files (and locations) the answer relies on")


TOOLS = [
    {"name": "list_files", "description": "List files under a directory of the workspace (relative path, '.' for the root).",
     "input_schema": {"type": "object", "properties": {"dir": {"type": "string"}}, "required": ["dir"],
                      "additionalProperties": False}},
    {"name": "read_file",
     "description": "Read a text, Markdown, CSV, code or PDF file from the workspace. Long files are returned in pages "
                    "of 20000 characters; use offset to continue.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "offset": {"type": "integer"}},
                      "required": ["path", "offset"], "additionalProperties": False}},
    {"name": "run_python",
     "description": "Run a Python script with the workspace as working directory (pandas, numpy and PyYAML are "
                    "installed; no network). Returns stdout and stderr. Each call is a fresh process.",
     "input_schema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"],
                      "additionalProperties": False}},
    {"name": "submit_answer", "description": "Submit the final answer. Call it exactly once, when you are done.",
     "input_schema": {
         "type": "object", "additionalProperties": False,
         "required": ["values", "summary", "transformations", "open_issues", "citations"],
         "properties": {
             "values": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                   "required": ["name", "value", "unit"],
                                                   "properties": {"name": {"type": "string"},
                                                                  "value": {"type": "number"},
                                                                  "unit": {"type": "string"}}}},
             "summary": {"type": "string"},
             "transformations": {"type": "array", "items": {"type": "string"}},
             "open_issues": {"type": "array", "items": {"type": "string"}},
             "citations": {"type": "array", "items": {"type": "string"}},
         }}},
]
TOOL_NAMES = {t["name"] for t in TOOLS}

SYSTEM = """You are a careful research agent working inside a sandboxed workspace directory.

You can use exactly these tools: list_files, read_file, run_python and submit_answer. No other tools exist in this
environment; calls to any other tool name fail. Paths are relative to the workspace root. run_python runs a fresh
Python process in the workspace root (pandas, numpy and PyYAML are available; there is no network access).

Work like a meticulous scientist: inspect the materials, follow their documentation and conventions exactly, never
invent missing information, and state what remains unresolved. Compute numbers with code rather than by hand.
When you are done, call submit_answer exactly once with every requested value."""


def _sanitize(block: dict[str, Any]) -> dict[str, Any] | None:
    t = block.get("type")
    if t == "text":
        return {"type": "text", "text": block.get("text", "")}
    if t == "thinking":
        return {"type": "thinking", "thinking": block.get("thinking", ""), "signature": block.get("signature", "")}
    if t == "redacted_thinking":
        return {"type": "redacted_thinking", "data": block.get("data", "")}
    if t == "tool_use":
        return {"type": "tool_use", "id": block["id"], "name": block["name"], "input": block.get("input", {})}
    return None


def _safe_path(workspace: Path, rel: str) -> Path:
    p = (workspace / rel).resolve()
    if p != workspace and workspace not in p.parents:
        raise ValueError(f"path {rel!r} is outside the workspace")
    return p


def tool_list_files(workspace: Path, rel: str) -> str:
    base = _safe_path(workspace, rel or ".")
    if not base.exists():
        return f"no such directory: {rel}"
    lines = []
    for p in sorted(base.rglob("*")):
        parts = set(p.relative_to(workspace).parts)
        if parts & HIDDEN or p.name.startswith(".agent_"):
            continue
        if p.is_file():
            lines.append(f"{p.relative_to(workspace).as_posix()}  ({p.stat().st_size} bytes)")
        if len(lines) >= 400:
            lines.append("... (truncated)")
            break
    return "\n".join(lines) or "(empty)"


def tool_read_file(workspace: Path, rel: str, offset: int = 0) -> str:
    p = _safe_path(workspace, rel)
    if not p.is_file():
        return f"no such file: {rel}"
    if p.suffix.lower() == ".pdf":
        with pdfplumber.open(p) as pdf:
            text = "\n\n".join(f"[page {i}]\n{page.extract_text() or ''}" for i, page in enumerate(pdf.pages, start=1))
    else:
        text = p.read_text(encoding="utf-8", errors="replace")
    offset = max(0, int(offset or 0))
    chunk = text[offset: offset + MAX_READ_CHARS]
    if offset + MAX_READ_CHARS < len(text):
        chunk += f"\n... [{len(text) - offset - MAX_READ_CHARS} more characters; call read_file with offset=" \
                 f"{offset + MAX_READ_CHARS}]"
    return chunk


class AgentRun:
    def __init__(self, llm: LLMClient, workspace: Path, model: str, task_prompt: str, run_id: str,
                 instructions: str | None = None, max_steps: int = 30, max_tokens: int = 16000):
        self.llm = llm
        self.workspace = Path(workspace).resolve()
        self.model = model
        self.task_prompt = task_prompt
        self.run_id = run_id
        self.instructions = instructions
        self.max_steps = max_steps
        self.max_tokens = max_tokens
        self.trace: list[dict[str, Any]] = []
        self.usage = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "calls": 0, "cost_usd": 0.0}
        self.invalid_tool_calls = 0
        self.python_calls: list[str] = []

    def _system(self) -> list[dict[str, Any]]:
        text = SYSTEM
        if self.instructions:
            text += "\n\nRepository instructions (from AGENTS.md in the workspace):\n\n" + self.instructions
        return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]

    def _call(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        msgs = json.loads(json.dumps(messages))
        last = msgs[-1]
        if isinstance(last["content"], list) and last["content"]:
            last["content"][-1]["cache_control"] = {"type": "ephemeral"}
        data = self.llm.raw_create(model=self.model, max_tokens=self.max_tokens, system=self._system(), tools=TOOLS,
                                   messages=msgs, cache_namespace=self.run_id)
        u = data.get("usage", {}) or {}
        inp, out = int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0)
        cr, cw = int(u.get("cache_read_input_tokens") or 0), int(u.get("cache_creation_input_tokens") or 0)
        self.usage["input"] += inp
        self.usage["output"] += out
        self.usage["cache_read"] += cr
        self.usage["cache_write"] += cw
        self.usage["calls"] += 1
        self.usage["cost_usd"] += estimate_cost(self.model, inp, out, cr, cw)
        return data

    def _execute(self, name: str, args: dict[str, Any]) -> tuple[str, bool]:
        if name not in TOOL_NAMES:
            self.invalid_tool_calls += 1
            return (f"Tool {name!r} is not available in this environment. Available tools: list_files, read_file, "
                    "run_python, submit_answer."), True
        try:
            if name == "list_files":
                return tool_list_files(self.workspace, str(args.get("dir", "."))), False
            if name == "read_file":
                return tool_read_file(self.workspace, str(args["path"]), int(args.get("offset") or 0)), False
            if name == "run_python":
                code = str(args["code"])
                self.python_calls.append(code)
                r = run_python(code, self.workspace)
                return f"exit code {r['exit_code']}\n{r['output']}", r["exit_code"] != 0
        except (ValueError, KeyError, OSError) as e:
            return f"error: {e}", True
        return "unknown tool", True

    def run(self) -> dict[str, Any]:
        t0 = time.time()
        listing = tool_list_files(self.workspace, ".")
        messages: list[dict[str, Any]] = [{"role": "user", "content": [
            {"type": "text", "text": f"Task:\n{self.task_prompt}\n\nWorkspace files:\n{listing}"}]}]
        answer: Answer | None = None
        status = "max_steps"
        nudged = False
        error = None
        for step in range(1, self.max_steps + 1):
            try:
                data = self._call(messages)
            except LLMError as e:
                status, error = "error", str(e)
                break
            content = [b for b in (_sanitize(x) for x in data.get("content", [])) if b]
            messages.append({"role": "assistant", "content": content or [{"type": "text", "text": "(empty)"}]})
            texts = [b["text"] for b in content if b["type"] == "text" and b["text"].strip()]
            calls = [b for b in content if b["type"] == "tool_use"]
            self.trace.append({"step": step, "stop_reason": data.get("stop_reason"), "text": "\n".join(texts)[:4000],
                               "tool_calls": [{"name": c["name"], "input": c["input"]} for c in calls],
                               "usage": data.get("usage")})
            if data.get("stop_reason") == "refusal":
                status = "refusal"
                break
            if not calls:
                if data.get("stop_reason") == "max_tokens":
                    messages.append({"role": "user", "content": [{"type": "text", "text":
                                     "Your reply was cut off. Continue, and keep each reply shorter."}]})
                    continue
                if nudged:
                    status = "no_answer"
                    break
                nudged = True
                messages.append({"role": "user", "content": [{"type": "text", "text":
                                 "Please finish by calling submit_answer with all requested values."}]})
                continue
            results = []
            for c in calls:
                if c["name"] == "submit_answer":
                    try:
                        answer = Answer.model_validate(c["input"])
                        out, err = "Answer received.", False
                    except ValidationError as e:
                        out, err = f"Invalid answer: {e}", True
                else:
                    out, err = self._execute(c["name"], c["input"])
                self.trace[-1].setdefault("results", []).append({"name": c["name"], "is_error": err,
                                                                 "output": out[:3000]})
                results.append({"type": "tool_result", "tool_use_id": c["id"], "content": out, "is_error": err})
            messages.append({"role": "user", "content": results})
            if answer is not None:
                status = "answered"
                break
        return {
            "run_id": self.run_id, "model": self.model, "status": status, "error": error,
            "answer": answer.model_dump() if answer else None, "steps": len(self.trace),
            "seconds": round(time.time() - t0, 1), "usage": {**self.usage, "cost_usd": round(self.usage["cost_usd"], 4)},
            "invalid_tool_calls": self.invalid_tool_calls,
            "used_repository_tools": any("research_tools" in c for c in self.python_calls),
            "python_calls": len(self.python_calls), "trace": self.trace, "finished_at": now_iso(),
        }
