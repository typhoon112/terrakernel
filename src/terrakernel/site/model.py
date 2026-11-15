"""Load everything a site needs from a built TerraKernel repository.

Read-only: the site is a view of the knowledge base, the build plan, the events of the last
build, agent runs and update reports. Nothing here calls a model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from terrakernel.models import EvidenceLink, Gap, KnowledgeObject, Relation, Source
from terrakernel.plan.spec import RepositorySpec
from terrakernel.project import Project


@dataclass
class RunRecord:
    data: dict[str, Any]

    @property
    def id(self) -> str:
        return self.data.get("run_id", "run")

    @property
    def setting(self) -> str:
        return self.data.get("setting", "?")

    @property
    def model(self) -> str:
        return self.data.get("model", "?")

    @property
    def grade(self) -> dict[str, Any] | None:
        return self.data.get("grade")


@dataclass
class SiteData:
    project: Project
    name: str
    goal: str
    model: str
    updated: str
    spec: RepositorySpec
    sources: list[Source]
    evidence: dict[str, Any]
    objects: dict[str, KnowledgeObject]
    links: dict[str, list[EvidenceLink]]
    relations: list[Relation]
    gaps: list[Gap]
    validation: dict[str, Any]
    state: dict[str, Any]
    events: list[dict[str, Any]]
    runs: list[RunRecord]
    updates: list[dict[str, Any]]
    config: dict[str, Any] = field(default_factory=dict)
    site_config: dict[str, Any] = field(default_factory=dict)
    kdocs: dict[str, dict[str, Any]] = field(default_factory=dict)

    # ------------------------------------------------------------- convenience
    def object(self, oid: str) -> KnowledgeObject | None:
        return self.objects.get(oid)

    def relations_of(self, oid: str) -> list[Relation]:
        return [r for r in self.relations if r.src == oid or r.dst == oid]

    def conflicts(self) -> list[Relation]:
        return [r for r in self.relations if r.type.value == "conflicts_with"]

    def open_gaps(self) -> list[Gap]:
        return [g for g in self.gaps if not g.resolved_by]

    def answered_gaps(self) -> list[Gap]:
        return [g for g in self.gaps if g.resolved_by]

    def evidence_of(self, oid: str) -> list[tuple[EvidenceLink, Any]]:
        out = []
        for lk in self.links.get(oid, []):
            ev = self.evidence.get(lk.evidence_id)
            if ev is not None:
                out.append((lk, ev))
        return out

    def source_of(self, eid_or_sid: str) -> Source | None:
        sid = eid_or_sid
        if eid_or_sid.startswith("ev:"):
            ev = self.evidence.get(eid_or_sid)
            sid = ev.source_id if ev else ""
        return next((s for s in self.sources if s.id == sid), None)

    def artifacts_using(self, oid: str) -> list[Any]:
        return [a for a in self.spec.artifacts if oid in a.objects]

    def docs_using(self, oid: str) -> list[Any]:
        return [a for a in self.artifacts_using(oid) if a.kind in ("knowledge_doc", "computation_doc")]

    def skills_using(self, oid: str) -> list[Any]:
        return [a for a in self.artifacts_using(oid) if a.kind == "skill"]

    def tools(self) -> list[dict[str, Any]]:
        reg = self.project.repo / "tools" / "research_tools" / "registry.json"
        if not reg.exists():
            return []
        return json.loads(reg.read_text()).get("tools", [])

    def tool_entry(self, name: str) -> dict[str, Any] | None:
        return next((t for t in self.tools() if t["name"] == name), None)

    def knowledge_docs(self) -> list[dict[str, Any]]:
        """Knowledge documents on disk: path, frontmatter, body (as rendered by the site)."""
        out = []
        kroot = self.project.repo / "knowledge"
        for f in sorted(kroot.rglob("*.md")):
            if f.name in ("index.md", "log.md"):
                continue
            text = f.read_text(encoding="utf-8")
            if not text.startswith("---"):
                continue
            end = text.find("\n---", 4)
            fm = yaml.safe_load(text[4:end]) or {}
            rel = f.relative_to(self.project.repo).as_posix()
            if (fm.get("x-terrakernel") or {}).get("evidence_for"):
                continue  # evidence companions are reached from their document, not listed
            out.append({"path": rel, "title": fm.get("title") or f.stem, "type": fm.get("type", ""),
                        "status": fm.get("status", "stable"), "frontmatter": fm, "body": text[end + 4:].strip(),
                        "objects": (fm.get("x-terrakernel") or {}).get("objects", [])})
        return out

    def counts(self) -> dict[str, Any]:
        by_type: dict[str, int] = {}
        for o in self.objects.values():
            by_type[o.type.value] = by_type.get(o.type.value, 0) + 1
        tools = self.tools()
        return {
            "sources": len(self.sources),
            "evidence": len(self.evidence),
            "objects": len(self.objects),
            "objects_by_type": by_type,
            "relations": len(self.relations),
            "conflicts": len(self.conflicts()),
            "gaps": len(self.gaps),
            "open_gaps": len(self.open_gaps()),
            "blocking_gaps": sum(g.severity.value == "blocking" for g in self.open_gaps()),
            "answered_gaps": len(self.answered_gaps()),
            "needs_review": sum(o.status.value == "needs_review" for o in self.objects.values()),
            "human_confirmed": sum(o.basis.value == "human_confirmed" for o in self.objects.values()),
            "tools": len(tools),
            "verified_tools": sum(t.get("status") == "verified" for t in tools),
            "tested_tools": sum(t.get("status") == "tested" for t in tools),
            "failed_tools": sum(t.get("status") == "failed" for t in tools),
            "docs": sum(a.kind == "knowledge_doc" for a in self.spec.artifacts),
            "computations": sum(a.kind == "computation_doc" for a in self.spec.artifacts),
            "skills": sum(a.kind == "skill" for a in self.spec.artifacts),
            "runs": len(self.runs),
            "updates": len(self.updates),
            "checks_pass": (self.validation.get("summary") or {}).get("pass", 0),
            "checks_fail": (self.validation.get("summary") or {}).get("fail", 0),
        }


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return default


def load_site_data(project: Project, site_config: str | Path | None = None) -> SiteData:
    cfg = project.config
    if project.spec_path.exists():
        spec = RepositorySpec.model_validate(yaml.safe_load(project.spec_path.read_text()))
    else:  # not planned yet: the site still shows materials, evidence and knowledge
        spec = RepositorySpec.model_construct(version="1", generated_at="", generated_by="", summary="", plan=None,
                                              artifacts=[], issues=[])
    kb = project.kb
    sources = kb.sources()
    evidence = {e.id: e for e in kb.evidence()}
    objects = {o.id: o for o in kb.objects()}
    links: dict[str, list[EvidenceLink]] = {}
    for lk in kb.links():
        links.setdefault(lk.object_id, []).append(lk)
    events = []
    if project.events_path.exists():
        for line in project.events_path.read_text().splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    runs = []
    if project.runs_dir.exists():
        for f in sorted(project.runs_dir.glob("*.json")):
            data = _load_json(f, None)
            if data:
                runs.append(RunRecord(data))
    updates = []
    upd_dir = project.state / "updates"
    if upd_dir.exists():
        for f in sorted(upd_dir.glob("*.json")):
            data = _load_json(f, None)
            if data:
                updates.append(data)
    site_cfg: dict[str, Any] = {}
    if site_config:
        p = Path(site_config)
        if p.exists():
            site_cfg = yaml.safe_load(p.read_text()) or {}
    state = project.load_state()
    validation = _load_json(project.validation_path, {})
    data = SiteData(
        project=project, name=site_cfg.get("title") or cfg.name, goal=cfg.goal, model=cfg.model,
        updated=(validation.get("at") or "")[:19].replace("T", " "), spec=spec, sources=sources, evidence=evidence,
        objects=objects, links=links, relations=kb.relations(), gaps=kb.gaps(), validation=validation, state=state,
        events=events, runs=runs, updates=updates, config=cfg.model_dump(mode="json"), site_config=site_cfg,
    )
    data.kdocs = {d["path"]: d for d in data.knowledge_docs()}
    return data
