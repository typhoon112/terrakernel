"""Lineage: source -> evidence -> object -> artifact dependencies, and impact analysis.

The lineage graph is what lets TerraKernel *manage* a repository after building it:
when a source changes, the evidence units that changed are known (stable IDs), the
objects grounded in them are known (evidence links), and every artifact records the
objects and other artifacts it depends on. Impact propagates along these edges.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from terrakernel.plan.spec import RepositorySpec
from terrakernel.project import Project
from terrakernel.util import now_iso, short_hash


def object_fingerprints(project: Project) -> dict[str, str]:
    """Content fingerprint of every object (what a doc or tool actually consumed)."""
    out = {}
    for o in project.kb.objects():
        payload = json.dumps({"name": o.name, "summary": o.summary, "attributes": o.attributes, "basis": o.basis.value,
                              "status": o.status.value}, sort_keys=True, default=str)
        out[o.id] = short_hash(payload, 16)
    return out


def build_lineage(project: Project, spec: RepositorySpec) -> dict[str, Any]:
    kb = project.kb
    sources = {s.id: {"path": s.path, "sha256": s.sha256} for s in kb.sources()}
    evidence = {e.id: {"source": e.source_id, "hash": e.content_hash} for e in kb.evidence()}
    links: dict[str, list[str]] = defaultdict(list)
    for lk in kb.links():
        links[lk.object_id].append(lk.evidence_id)
    objects = {}
    fps = object_fingerprints(project)
    for o in kb.objects():
        derived_from = sorted(set(o.attributes.get("members", []))) if o.produced_by.endswith("+reconcile") else []
        objects[o.id] = {"evidence": sorted(set(links.get(o.id, []))), "derived_from": derived_from,
                         "fingerprint": fps[o.id], "sources": o.source_ids, "status": o.status.value}
    artifacts = {}
    for a in spec.artifacts:
        artifacts[a.id] = {"path": a.path, "kind": a.kind, "objects": a.objects, "depends_on": a.depends_on,
                           "object_fingerprints": {oid: fps.get(oid) for oid in a.objects}, "status": a.status}
    lineage = {"generated_at": now_iso(), "sources": sources, "evidence": evidence, "objects": objects,
               "artifacts": artifacts}
    project.lineage_path.write_text(json.dumps(lineage, indent=1, ensure_ascii=False))
    return lineage


def load_lineage(project: Project) -> dict[str, Any] | None:
    if not project.lineage_path.exists():
        return None
    return json.loads(project.lineage_path.read_text())


def impacted_artifacts(lineage: dict[str, Any], changed_objects: set[str]) -> dict[str, list[str]]:
    """Artifacts affected by a set of changed objects, with the reason chain for each."""
    reasons: dict[str, list[str]] = {}
    arts = lineage.get("artifacts", {})
    for aid, a in arts.items():
        hit = sorted(set(a.get("objects", [])) & changed_objects)
        if hit:
            reasons[aid] = [f"uses changed object {h}" for h in hit]
    changed = True
    while changed:
        changed = False
        for aid, a in arts.items():
            if aid in reasons:
                continue
            deps = [d for d in a.get("depends_on", []) if d in reasons]
            if deps:
                reasons[aid] = [f"depends on {d}" for d in deps]
                changed = True
    return reasons
