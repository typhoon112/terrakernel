"""Compile knowledge: OKF v0.2 knowledge documents, computation documents and the bundle index.

Every concept document gets frontmatter following the Open Knowledge Format v0.2
(``type``, ``title``, ``description``, ``tags``, ``status``, ``generated``, ``verified``,
``sources``), a model-written body whose factual statements are footnoted with knowledge
object IDs, and TerraKernel-generated footnote definitions plus an evidence appendix
that quotes the exact source locations. Documents whose body cites unknown objects or
leaves facts unattributed are rewritten once and otherwise marked ``status: draft``.

Each verified or tested tool becomes an ``Attested Computation`` concept (OKF §10)
pointing at its implementation, tests and the evidence the tests come from.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from terrakernel.builtin import skill_body
from terrakernel.llm.client import LLMClient
from terrakernel.models import Basis, KnowledgeObject, ObjectStatus
from terrakernel.plan.spec import DocPlan, RepositoryPlan
from terrakernel.project import Project
from terrakernel.util import now_iso, relpath, write_text_stable

FOOTNOTE_RE = re.compile(r"\[\^([^\]\s]+)\]")
OKF_VERSION = "0.2"


def short_ids(objects: list[KnowledgeObject]) -> dict[str, str]:
    """Short, stable citation keys for a document: s1, s2, ... in the order objects are listed."""
    return {o.id: f"s{i}" for i, o in enumerate(objects, start=1)}


def footnote_key(object_id: str) -> str:
    """OKF footnote labels are ``sources[].id``; object IDs are used directly but made label-safe."""
    return re.sub(r"[^A-Za-z0-9_:/.\-]", "-", object_id)


def doc_frontmatter(project: Project, plan_doc: DocPlan, objects: list[KnowledgeObject], status: str,
                    verified_by: list[dict[str, str]] | None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    kb = project.kb
    cfg = project.config
    doc_dir = (project.repo / "knowledge" / plan_doc.path).parent
    sources_rel = relpath(project.repo / "sources", doc_dir)

    def _source_resource(source_path: str) -> str:
        return f"{sources_rel}/{source_path}"

    sources = []
    short = short_ids(objects)
    for o in objects:
        src_paths = []
        for sid in o.source_ids:
            s = kb.source(sid)
            if s:
                src_paths.append(s.path)
        locs = []
        for lk in kb.links(o.id):
            ev = kb.evidence_by_ids([lk.evidence_id]).get(lk.evidence_id)
            if ev:
                locs.append(ev.locator.short() or ev.id)
        entry: dict[str, Any] = {
            "id": short[o.id],
            "resource": _source_resource(src_paths[0]) if len(src_paths) == 1 else
            ("scope: knowledge derived from " + ", ".join(src_paths) if src_paths else "scope: terrakernel knowledge base"),
            "title": f"{o.name} ({o.type.value}, {o.basis.value})" + (f" — {'; '.join(locs[:2])}" if locs else ""),
            "object": o.id,
        }
        if o.basis == Basis.human_confirmed and o.produced_by.startswith("human:"):
            entry["author"] = o.produced_by
        sources.append(entry)
    fm: dict[str, Any] = {
        "type": plan_doc.okf_type,
        "title": plan_doc.title,
        "description": plan_doc.description,
        "tags": sorted({o.type.value for o in objects} | set(plan_doc.task_ids)),
        "status": status,
        "generated": {"by": f"{cfg.actor}+{cfg.model}", "at": now_iso()},
    }
    if verified_by:
        fm["verified"] = verified_by
    fm["sources"] = sources
    fm["x-terrakernel"] = {"objects": [o.id for o in objects], **(extra or {})}
    return fm


def render_okf(frontmatter: dict[str, Any], body: str) -> str:
    fm = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True, width=110).strip()
    return f"---\n{fm}\n---\n\n{body.strip()}\n"


def _object_payload(project: Project, o: KnowledgeObject) -> dict[str, Any]:
    kb = project.kb
    evidence = []
    for lk in kb.links(o.id)[:4]:
        ev = kb.evidence_by_ids([lk.evidence_id]).get(lk.evidence_id)
        if ev:
            evidence.append({"locator": f"{kb.source(ev.source_id).path if kb.source(ev.source_id) else ev.source_id} "
                                        f"{ev.locator.short()}", "quote": lk.quote})
    attrs = {k: v for k, v in o.attributes.items() if v not in (None, "", [], {})}
    return {"id": o.id, "type": o.type.value, "name": o.name, "aliases": o.aliases, "summary": o.summary,
            "basis": o.basis.value, "basis_note": o.basis_note, "status": o.status.value, "attributes": attrs,
            "evidence": evidence}


def doc_body_prompt(project: Project, plan_doc: DocPlan, objects: list[KnowledgeObject], plan: RepositoryPlan,
                    tool_status: dict[str, str], issues: list[str] | None = None, previous: str | None = None) -> str:
    from terrakernel.compile.context import gap_context

    kb = project.kb
    ids = {o.id for o in objects}
    rels = [r for r in kb.relations() if r.src in ids or r.dst in ids]
    tasks = [task for task in project.config.tasks if task.id in plan_doc.task_ids]
    task_text = "\n".join([plan_doc.title, plan_doc.description,
                           *[f"{task.title} {task.prompt} {' '.join(task.acceptance)}" for task in tasks]])
    gaps = gap_context(project, ids, task_text)
    links = [f"- [{d.title}](/{d.path}): {d.description}" for d in plan.docs if d.path != plan_doc.path]
    links.append("- [Complete gap register](/gaps.md): all open and resolved gaps, including omitted context")
    tools = [f"- `{t.name}` ({t.strategy}, status {tool_status.get(t.name, 'not built')}): {t.purpose}; "
             f"methods {t.method_ids}" for t in plan.tools if set(t.method_ids) & ids or t.capability_id in ids]
    parts = [
        f"Document: {plan_doc.title} ({plan_doc.okf_type})", f"Purpose: {plan_doc.description}",
        f"Repository goal: {project.config.goal}", "",
        "Knowledge objects. Cite each fact with the object's `cite` key, for example [^s3]:",
        *[json.dumps({"cite": short_ids(objects)[o.id], **_object_payload(project, o)}, ensure_ascii=False, default=str)
          for o in objects],
        "", "Relations involving these objects:",
        *([f"- {r.type.value}: {r.src} -> {r.dst}. {r.note}" for r in rels] or ["- none"]),
        "", "Candidate gap reports (cross-check against the supplied objects and tool status):",
        gaps.text,
        "", "Repository tools implementing these objects:", *(tools or ["- none"]),
        "", "Other documents you may link to:", *(links or ["- none"]),
    ]
    if issues and previous:
        parts += ["", "Your previous draft had these problems:", *[f"- {i}" for i in issues], "", "Previous draft:",
                  previous, "", "Return the complete corrected body."]
    return "\n".join(parts)


META_RE = re.compile(
    r"\b(I (left|described|kept|added|removed|could not|did not|have)|If you want|citable|the (given|provided) "
    r"(ID |object )?list|previous draft|as instructed|footnote definitions)\b", re.I)


def check_body(body: str, allowed: set[str]) -> list[str]:
    problems = []
    meta = sorted({m.group(0) for m in META_RE.finditer(body)})
    if meta:
        problems.append(f"remove notes addressed to the editor (e.g. {meta[:3]}); write only document content")
    cited = set(FOOTNOTE_RE.findall(body))
    unknown = sorted(c for c in cited if c not in allowed)
    if unknown:
        problems.append(f"footnotes use unknown cite keys: {unknown[:10]}; use only the `cite` keys given (s1, s2, ...)")
    if not cited:
        problems.append("no statement is attributed with an object footnote")
    if re.search(r"^\[\^[^\]]+\]:", body, flags=re.M):
        problems.append("do not write footnote definitions; TerraKernel generates them")
    if re.search(r"^# ", body, flags=re.M):
        problems.append("do not use a top-level '#' heading")
    # factual lines without a footnote (heuristic: table rows and sentences with digits or units)
    unattributed = [ln for ln in body.splitlines() if ln.startswith("|") and not ln.startswith("|---")
                    and re.search(r"\d", ln) and "[^" not in ln and not re.match(r"^\|\s*[-:| ]+\|?$", ln)]
    header_rows = [ln for ln in unattributed if ln.count("|") > 2 and not re.search(r"\d", ln.split("|")[1])]
    if len(unattributed) - len(header_rows) > 2:
        problems.append(f"{len(unattributed) - len(header_rows)} table rows with numbers have no footnote")
    return problems


def evidence_companion(project: Project, plan_doc: DocPlan, objects: list[KnowledgeObject]) -> tuple[str, str]:
    """Verbatim evidence for a document, written to ``knowledge/evidence/<doc>`` and loaded on demand.

    Returns (path relative to the repository, file text). The file is plain Markdown without
    frontmatter fields beyond ``type`` so it stays a valid OKF concept.
    """
    kb = project.kb
    short = short_ids(objects)
    rel = f"knowledge/evidence/{plan_doc.path.replace('/', '--')}"
    depth = "../../"
    lines = ["---", "type: Reference", f"title: Evidence for {plan_doc.title}",
             f"description: Verbatim quotes and locations supporting knowledge/{plan_doc.path}.",
             "x-terrakernel: {evidence_for: " + json.dumps(f"knowledge/{plan_doc.path}") + "}", "---", "",
             f"# Evidence for {plan_doc.title}", "",
             f"Each entry is one source cited in [{plan_doc.title}](/{plan_doc.path}); the key matches the "
             "footnote label used there.", ""]
    for o in objects:
        lines.append(f"## {short[o.id]} · {o.name}")
        lines.append("")
        lines.append(f"`{o.id}` ({o.type.value}, {o.basis.value})" + (f": {o.basis_note}" if o.basis_note else ""))
        lines.append("")
        for lk in kb.links(o.id)[:6]:
            ev = kb.evidence_by_ids([lk.evidence_id]).get(lk.evidence_id)
            if not ev:
                continue
            src = kb.source(ev.source_id)
            path = src.path if src else ev.source_id
            quote = (lk.quote or "").replace("\n", " ").strip()
            lines.append(f"- [{path}]({depth}sources/{path}) {ev.locator.short()}".rstrip()
                         + (f": “{quote[:400]}”" if quote else ""))
        lines.append("")
    return rel, "\n".join(lines).rstrip() + "\n"


def footnote_definitions(objects: list[KnowledgeObject], cited: list[str]) -> str:
    """Compact footnote definitions: short key -> object name (details live in the frontmatter)."""
    short = short_ids(objects)
    by_id = {o.id: o for o in objects}
    return "\n".join(f"[^{short[oid]}]: {by_id[oid].name}" for oid in cited if oid in by_id) + "\n"


def _fix_relative_source_links(text: str, doc_path: Path, repo: Path) -> str:
    rel = relpath(repo / "sources", doc_path.parent)
    return text.replace("](../sources/", f"]({rel}/")


def compile_doc(project: Project, llm: LLMClient, plan_doc: DocPlan, plan: RepositoryPlan, tool_status: dict[str, str],
                model: str) -> dict[str, Any]:
    kb = project.kb
    repo = project.repo
    objects = [o for o in (kb.object(i) for i in plan_doc.object_ids) if o is not None]
    short = short_ids(objects)
    allowed = set(short.values())
    system = skill_body("write-knowledge-docs")
    body = llm.text(doc_body_prompt(project, plan_doc, objects, plan, tool_status), system=system, model=model,
                    max_tokens=12000)
    problems = check_body(body, allowed)
    if problems:
        body = llm.text(doc_body_prompt(project, plan_doc, objects, plan, tool_status, problems, body), system=system,
                        model=model, max_tokens=12000)
        problems = check_body(body, allowed)
    body = re.sub(r"^\[\^[^\]]+\]:.*$", "", body, flags=re.M).strip()
    # drop a trailing editor-facing section if the model still appended one
    body = re.split(r"\n#{2,3} (Notes? (for|to) the (editor|reviewer)|Editorial notes?|Issues with (the|this) (draft|input))",
                    body, maxsplit=1)[0].rstrip()
    # unknown footnotes are removed rather than shipped as broken attributions
    body = FOOTNOTE_RE.sub(lambda m: m.group(0) if m.group(1) in allowed else "", body)
    key_to_id = {v: k for k, v in short.items()}
    cited = [key_to_id[c] for c in dict.fromkeys(FOOTNOTE_RE.findall(body)) if c in key_to_id]
    reviewed = [o for o in objects if o.status == ObjectStatus.needs_review]
    status = "draft" if problems or reviewed else "stable"
    ev_rel, ev_text = evidence_companion(project, plan_doc, objects)
    write_text_stable(repo / ev_rel, ev_text)
    fm = doc_frontmatter(project, plan_doc, objects, status, None,
                         extra={"tasks": plan_doc.task_ids, "check_problems": problems, "evidence": ev_rel})
    path = repo / "knowledge" / plan_doc.path
    ev_link = relpath(repo / ev_rel, path.parent)
    tail = (f"\n\nVerbatim quotes and source locations for every citation: [evidence]({ev_link}).\n\n"
            + footnote_definitions(objects, cited))
    text = render_okf(fm, f"# {plan_doc.title}\n\n" + body + tail)
    write_text_stable(path, text)
    return {"path": f"knowledge/{plan_doc.path}", "status": status, "objects": len(objects), "cited": len(cited),
            "problems": problems, "evidence": ev_rel}


def compile_computation_doc(project: Project, entry: dict[str, Any], plan: RepositoryPlan) -> str | None:
    """OKF §10 Attested Computation concept for a built tool."""
    if entry.get("status") not in ("verified", "tested"):
        return None
    kb = project.kb
    repo = project.repo
    cfg = project.config
    tool = next(t for t in plan.tools if t.name == entry["name"])
    rel_path = Path(entry["knowledge"])
    path = repo / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    impl = relpath(repo / "tools" / "research_tools" / "tools" / f"{tool.name}.py", path.parent)
    test = relpath(repo / entry["test_file"], path.parent)
    objects = [o for o in (kb.object(i) for i in entry["objects"]) if o]
    sources = []
    for o in objects:
        srcs = [kb.source(s).path for s in o.source_ids if kb.source(s)]
        sources.append({"id": footnote_key(o.id),
                        "resource": f"../../sources/{srcs[0]}" if len(srcs) == 1 else "scope: " + ", ".join(srcs),
                        "title": f"{o.name} ({o.type.value})"})
    verified = None
    if entry["status"] == "verified":
        verified = [{"by": "process:terrakernel-validate", "at": now_iso()}]
    fm: dict[str, Any] = {
        "type": "Attested Computation",
        "title": tool.name,
        "description": tool.purpose,
        "tags": ["computation", tool.strategy],
        "status": "stable" if entry["status"] == "verified" else "draft",
        "runtime": "python",
        "parameters": [{"name": i.name, "type": "number[]" if i.kind == "series" else i.kind, "required": True,
                        **({"unit": i.unit} if i.unit else {})} for i in tool.inputs],
        "computation": impl,
        "executor": {"resource": "../../tools/mcp_server.py",
                     "receipt": ["tool", "value", "unit", "inputs", "sample"]},
        "attester": {"resource": test},
        "generated": {"by": f"{cfg.actor}+{cfg.model}", "at": now_iso()},
    }
    if verified:
        fm["verified"] = verified
    fm["sources"] = sources
    fm["x-terrakernel"] = {"strategy": tool.strategy, "status": entry["status"], "tests": entry.get("tests"),
                           "reference_cases": entry.get("reference_cases", 0), "reuse": entry.get("reuse")}
    method_names = ", ".join(f"{o.name}[^{footnote_key(o.id)}]" for o in objects if o.type.value == "method")
    lines = [f"# {tool.name}", "", tool.purpose, "", "## Computation", "",
             f"Implemented in [`{impl}`]({impl}) (strategy: **{tool.strategy}**). "
             + (f"It reuses `{entry['reuse']['symbol']}` from `{entry['reuse']['source']}` unchanged and adds input checks."
                if entry.get("reuse") else "TerraKernel implemented it from the documented definition.")
             + (f" Definition: {method_names}." if method_names else ""), "",
             "| Input | Kind | Unit | Description |", "|---|---|---|---|"]
    lines += [f"| `{i.name}` | {i.kind} | {i.unit or ''} | {i.description} |" for i in tool.inputs]
    lines += ["", f"Output: {tool.output_description}" + (f" ({tool.output_unit})" if tool.output_unit else ""), "",
              "## Verification", "",
              f"Status: **{entry['status']}**. Tests: {entry.get('tests', {}).get('passed', 0)} passed, "
              f"{entry.get('tests', {}).get('failed', 0)} failed ([`{test}`]({test})).", ""]
    test_src = (repo / entry["test_file"]).read_text()
    m = re.search(r"REFERENCE_CASES = (\[.*?\])\n\n", test_src, flags=re.S)
    cases = json.loads(m.group(1)) if m else []
    if cases:
        lines += ["Reference cases taken from the materials (inputs and expected values are quoted, not computed):", "",
                  "| Case | Expected | Stated in | Quote |", "|---|---|---|---|"]
        for c in cases:
            ev = kb.evidence_by_ids([c["source"]]).get(c["source"])
            where = f"{kb.source(ev.source_id).path} {ev.locator.short()}" if ev and kb.source(ev.source_id) else c["source"]
            q = c["quote"].replace("\n", " ").replace("|", "\\|")
            lines.append(f"| {c['id']} | {c['expected']} ± {c['abs_tol']:.3g} | {where} | “{q}” |")
        lines.append("")
    else:
        lines += ["No reference values were available in the materials; only generic properties were tested.", ""]
    if tool.notes:
        lines += ["## Notes", "", tool.notes, ""]
    lines += [f"[^{footnote_key(o.id)}]: {o.name} ({o.type.value}, {o.basis.value})" for o in objects]
    write_text_stable(path, render_okf(fm, "\n".join(lines)))
    return str(rel_path)


def write_index(project: Project, plan: RepositoryPlan, doc_results: list[dict[str, Any]],
                computations: list[str]) -> None:
    repo = project.repo
    kroot = repo / "knowledge"
    groups: dict[str, list[str]] = {}
    for d in plan.docs:
        folder = d.path.split("/")[0] if "/" in d.path else "General"
        status = next((r["status"] for r in doc_results if r["path"] == f"knowledge/{d.path}"), "missing")
        flag = "" if status == "stable" else f" (status: {status})"
        groups.setdefault(folder, []).append(f"* [{d.title}]({d.path}) - {d.description}{flag}")
    if computations:
        groups["computations"] = []
        for c in computations:
            fm = yaml.safe_load((repo / c).read_text().split("---")[1])
            groups["computations"].append(f"* [{fm['title']}]({Path(c).relative_to('knowledge').as_posix()}) - "
                                          f"{fm['description']} (Attested Computation, {fm['x-terrakernel']['status']})")
    write_catalog(project)
    lines = ["---", f'okf_version: "{OKF_VERSION}"', "---", "",
             "# Complete knowledge catalog", "",
             "* [All extracted objects](catalog.md) — includes knowledge outside the task guides.",
             "* [Machine-readable catalog](catalog.jsonl) — objects, original quotes and source locations.", ""]
    lines += ["* [All open and resolved gaps](gaps.md) — the full register beyond task-specific selections.",
              "* [Machine-readable gaps](gaps.jsonl) — gap IDs, status and original evidence locations.", ""]
    for folder, items in groups.items():
        lines.append(f"# {folder.replace('-', ' ').capitalize()}")
        lines.append("")
        lines += items
        lines.append("")
    write_text_stable(kroot / "index.md", "\n".join(lines))
    # per-folder indexes for progressive disclosure
    for folder in {d.path.split("/")[0] for d in plan.docs if "/" in d.path} | ({"computations"} if computations else set()):
        items = [i.replace(f"]({folder}/", "](") for i in groups.get(folder, [])]
        (kroot / folder).mkdir(parents=True, exist_ok=True)
        write_text_stable(kroot / folder / "index.md", f"# {folder.replace('-', ' ').capitalize()}\n\n" + "\n".join(items) + "\n")


def write_catalog(project: Project) -> None:
    """Publish every object and its provenance, independently of planner selection."""
    kb = project.kb
    sources = {s.id: s for s in kb.sources()}
    links: dict[str, list] = {}
    for link in kb.links():
        links.setdefault(link.object_id, []).append(link)
    gaps = kb.gaps()
    evidence = kb.evidence_by_ids({link.evidence_id for group in links.values() for link in group}
                                  | {eid for gap in gaps for eid in gap.evidence_ids})
    rows = []
    body = ["# Complete knowledge catalog", "",
            "Task guides organize a selected working set. This catalog preserves every extracted object, "
            "including items awaiting review. Search the JSONL file by name, source or object ID for "
            "full attributes, quotations and locators. Original evidence remains in the knowledge database.",
            "", "[Download the searchable catalog](catalog.jsonl)", ""]
    for obj in kb.objects():
        row = obj.model_dump(mode="json")
        refs = []
        for link in links.get(obj.id, []):
            ev = evidence.get(link.evidence_id)
            source = sources.get(ev.source_id) if ev else None
            refs.append({"evidence_id": link.evidence_id, "quote": link.quote,
                         "source": source.path if source else None,
                         "locator": ev.locator.model_dump(mode="json") if ev else None,
                         "match_score": link.match_score})
        row["evidence"] = refs
        rows.append(json.dumps(row, ensure_ascii=False))
        # Plain text avoids treating source-supplied bracket syntax as Markdown links.
        name = obj.name.replace("[", "\\[").replace("]", "\\]").replace("\n", " ")
        body.append(f"- **{name}** ({obj.type.value}; {obj.basis.value}; {obj.status.value}) — `{obj.id}`")
    fm = {"type": "Reference", "title": "Complete knowledge catalog",
          "description": "Deterministic inventory of all extracted knowledge, with full provenance in JSONL.",
          "status": "stable", "generated": {"by": project.config.actor, "at": now_iso()},
          "sources": [{"id": "kb", "resource": "../.terrakernel/kb.sqlite"}],
          "x-terrakernel": {"catalog": True}}
    write_text_stable(project.repo / "knowledge" / "catalog.jsonl", "\n".join(rows) + "\n")
    write_text_stable(project.repo / "knowledge" / "catalog.md", render_okf(fm, "\n".join(body)))
    gap_rows = []
    gap_body = ["# Complete gap register", "",
                "This register preserves every open and resolved gap. Artifact prompts contain only a bounded "
                "selection; omission from a prompt does not resolve a gap.", "",
                "Open entries are unconfirmed reports from limited evidence batches or reconciliation groups; "
                "an answer may exist elsewhere, so check current knowledge and tools before concluding that "
                "material or a capability is missing.", "",
                "[Download all gaps and source locations](gaps.jsonl)", ""]
    for gap in gaps:
        row = gap.model_dump(mode="json")
        row["evidence"] = []
        for eid in gap.evidence_ids:
            ev = evidence.get(eid)
            source = sources.get(ev.source_id) if ev else None
            row["evidence"].append({"evidence_id": eid, "source": source.path if source else None,
                                    "locator": ev.locator.model_dump(mode="json") if ev else None})
        gap_rows.append(json.dumps(row, ensure_ascii=False))
        # Descriptions are source-derived text, not Markdown links to trust or validate.
        description = gap.description.replace("[", "\\[").replace("]", "\\]")
        state = "resolved" if gap.resolved_by else "open"
        gap_body += [f"## {gap.id}", "", f"{state}; {gap.severity.value}", "", description, ""]
        if gap.subject_id:
            gap_body += [f"Subject: `{gap.subject_id}`", ""]
        if gap.resolved_by:
            resolution = (gap.resolution or "").replace("[", "\\[").replace("]", "\\]")
            gap_body += [f"Resolved by: `{gap.resolved_by}`", "", resolution, ""]
    gap_fm = {**fm, "title": "Complete gap register",
              "description": "All open and resolved gaps, with original evidence locations in JSONL.",
              "x-terrakernel": {"gap_register": True}}
    write_text_stable(project.repo / "knowledge" / "gaps.jsonl", "\n".join(gap_rows) + "\n")
    write_text_stable(project.repo / "knowledge" / "gaps.md", render_okf(gap_fm, "\n".join(gap_body)))


def append_log(project: Project, entries: list[str]) -> None:
    path = project.repo / "knowledge" / "log.md"
    today = now_iso()[:10]
    existing = path.read_text() if path.exists() else "# Directory Update Log\n"
    body = existing.split("\n", 1)[1] if existing.startswith("# Directory Update Log") else existing
    block = f"\n## {today}\n" + "\n".join(f"* {e}" for e in entries) + "\n"
    if body.startswith(block):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_stable(path, "# Directory Update Log\n" + block + body)
