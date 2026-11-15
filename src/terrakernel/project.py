"""Project layout on disk.

A TerraKernel project *is* the generated research repository. Everything the builder
needs to manage it lives under ``<repo>/.terrakernel/``:

    .terrakernel/
      project.yaml     goal, tasks, materials path, models, target agents
      kb.sqlite        source knowledge base (sources, evidence, objects, relations, gaps)
      assets/          page renders and figure crops referenced by evidence
      spec.yaml        Repository Spec produced by the planner
      lineage.json     source -> evidence -> object -> artifact dependencies
      validation.json  latest validation report
      state.json       pipeline stage status and input fingerprints
      events.jsonl     append-only progress events
      llm-cache/       content-addressed model responses (replayable)
      runs/            agent task runs (traces)
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from terrakernel import __version__
from terrakernel.store import KnowledgeBase
from terrakernel.util import now_iso

STATE_DIR = ".terrakernel"
HUMAN_SOURCE_ID = "human_answers"
HUMAN_SOURCE_FILE = "human_answers.md"


class ReportValue(BaseModel):
    """A number the agent must report for a task (graded against the expected answer)."""

    name: str
    description: str
    unit: str | None = None


class TaskSpec(BaseModel):
    """A research task the generated repository must support."""

    id: str
    title: str
    prompt: str  # what an agent is asked to do
    acceptance: list[str] = Field(default_factory=list)  # what a correct answer must contain or respect
    report_values: list[ReportValue] = Field(default_factory=list)
    expected: str | None = None  # optional absolute path to the expected answer JSON (for grading)


class ProjectConfig(BaseModel):
    name: str
    goal: str
    materials: str  # absolute path, or a path relative to the generated repository
    tasks: list[TaskSpec] = Field(default_factory=list)
    model: str = "claude-opus-5-5"
    extract_model: str | None = None
    target_agents: list[str] = Field(default_factory=lambda: ["claude-code", "codex"])
    license: str = "Apache-2.0"
    created: str = Field(default_factory=now_iso)
    terrakernel_version: str = __version__

    @property
    def actor(self) -> str:
        return f"terrakernel/{self.terrakernel_version}"


class Project:
    def __init__(self, repo_dir: Path):
        self.repo = Path(repo_dir).resolve()
        self.state = self.repo / STATE_DIR
        self._kb: KnowledgeBase | None = None
        self._events_lock = threading.Lock()
        self._listeners: list[Any] = []

    # ------------------------------------------------------------------ paths
    @property
    def config_path(self) -> Path:
        return self.state / "project.yaml"

    @property
    def kb_path(self) -> Path:
        return self.state / "kb.sqlite"

    @property
    def assets_dir(self) -> Path:
        return self.state / "assets"

    @property
    def llm_cache_dir(self) -> Path:
        return self.state / "llm-cache"

    @property
    def runs_dir(self) -> Path:
        return self.state / "runs"

    @property
    def spec_path(self) -> Path:
        return self.state / "spec.yaml"

    @property
    def lineage_path(self) -> Path:
        return self.state / "lineage.json"

    @property
    def validation_path(self) -> Path:
        return self.state / "validation.json"

    @property
    def state_path(self) -> Path:
        return self.state / "state.json"

    @property
    def events_path(self) -> Path:
        return self.state / "events.jsonl"

    @property
    def materials_dir(self) -> Path:
        path = Path(self.config.materials)
        return path if path.is_absolute() else (self.repo / path).resolve()

    @property
    def answers_path(self) -> Path:
        """Answers that people gave to open questions (managed by `terrakernel answer`)."""
        return self.state / HUMAN_SOURCE_FILE

    def source_file(self, source: Any) -> Path:
        if source.id == HUMAN_SOURCE_ID:
            return self.answers_path
        return self.materials_dir / source.path

    # ------------------------------------------------------------------ lifecycle
    @classmethod
    def create(cls, repo_dir: Path, config: ProjectConfig) -> Project:
        p = cls(repo_dir)
        p.state.mkdir(parents=True, exist_ok=True)
        p.save_config(config)
        return p

    @classmethod
    def open(cls, repo_dir: Path) -> Project:
        p = cls(repo_dir)
        if not p.config_path.exists():
            raise FileNotFoundError(f"{p.repo} is not a TerraKernel repository (missing {STATE_DIR}/project.yaml)")
        return p

    @property
    def config(self) -> ProjectConfig:
        data = yaml.safe_load(self.config_path.read_text())
        return ProjectConfig.model_validate(data)

    def save_config(self, config: ProjectConfig) -> None:
        self.state.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False, allow_unicode=True)
        )

    @property
    def kb(self) -> KnowledgeBase:
        if self._kb is None:
            self._kb = KnowledgeBase(self.kb_path)
        return self._kb

    def close(self) -> None:
        if self._kb is not None:
            self._kb.close()
            self._kb = None

    # ------------------------------------------------------------------ state
    def load_state(self) -> dict[str, Any]:
        if self.state_path.exists():
            return json.loads(self.state_path.read_text())
        return {"stages": {}}

    def save_state(self, state: dict[str, Any]) -> None:
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False))
        tmp.replace(self.state_path)

    def add_model_cost(self, calls: int, cost_usd: float) -> None:
        """Add model calls made on this repository (builds and updates) to the running total."""
        if not calls and not cost_usd:
            return
        state = self.load_state()
        total = state.setdefault("model_cost_total", {"model_calls": 0, "cost_usd_estimate": 0.0})
        total["model_calls"] += calls
        total["cost_usd_estimate"] = round(total["cost_usd_estimate"] + cost_usd, 4)
        self.save_state(state)

    def total_model_cost(self) -> dict[str, Any]:
        """Model calls and estimated cost of all builds and updates of this repository."""
        state = self.load_state()
        if "model_cost_total" in state:
            return state["model_cost_total"]
        stages = state.get("stages", {}).values()  # repositories built before the total was kept
        return {"model_calls": sum(st.get("model_calls", 0) or 0 for st in stages),
                "cost_usd_estimate": round(sum(st.get("cost_usd_estimate", 0) or 0 for st in stages), 4)}

    # ------------------------------------------------------------------ events
    def add_listener(self, fn: Any) -> None:
        self._listeners.append(fn)

    def emit(self, stage: str, kind: str, message: str, **data: Any) -> dict[str, Any]:
        event = {"at": now_iso(), "stage": stage, "kind": kind, "message": message}
        if data:
            event["data"] = data
        with self._events_lock:
            self.state.mkdir(parents=True, exist_ok=True)
            with open(self.events_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        for fn in self._listeners:
            try:
                fn(event)
            except Exception:  # listeners must never break the pipeline
                pass
        return event
