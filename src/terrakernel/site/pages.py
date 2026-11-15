"""HTML pages for the site, composed from the loaded repository data."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

from terrakernel.site import assets as A
from terrakernel.site import charts
from terrakernel.site.i18n import bi, tw
from terrakernel.site.model import SiteData
from terrakernel.site.render import md_to_html, split_frontmatter

TYPE_LABEL = {
    "concept": "concept", "claim": "claim", "method": "method", "dataset": "dataset", "constraint": "constraint",
    "capability": "capability",
}

LANG_SCRIPT = """
<script>
(function () {
  var lang = localStorage.getItem("tk-lang") || "en";
  function apply(l) {
    document.body.classList.toggle("zh", l === "zh");
    document.documentElement.lang = l === "zh" ? "zh-CN" : "en";
    document.querySelectorAll(".i18n").forEach(function (el) {
      var t = el.getAttribute("data-" + l);
      if (t !== null) el.textContent = t;
    });
    var b = document.querySelector(".lang");
    if (b) b.textContent = l === "zh" ? "English" : "中文";
  }
  apply(lang);
  var btn = document.querySelector(".lang");
  if (btn) btn.addEventListener("click", function () {
    lang = lang === "zh" ? "en" : "zh";
    localStorage.setItem("tk-lang", lang);
    apply(lang);
  });
  document.querySelectorAll("[data-play]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var box = document.getElementById(btn.getAttribute("data-play"));
      var items = box.querySelectorAll(".step-run");
      var playing = btn.getAttribute("data-state") === "playing";
      if (playing) { btn.setAttribute("data-state", "paused"); btn.textContent = "▶"; return; }
      btn.setAttribute("data-state", "playing");
      btn.textContent = "⏸";
      var i = 0;
      items.forEach(function (it) { it.classList.remove("on"); });
      function next() {
        if (btn.getAttribute("data-state") !== "playing") return;
        if (i >= items.length) { btn.setAttribute("data-state", "done"); btn.textContent = "↻"; return; }
        items[i].classList.add("on");
        items[i].scrollIntoView({block: "nearest", behavior: "smooth"});
        i += 1;
        setTimeout(next, 1400);
      }
      next();
    });
  });
  document.querySelectorAll(".chip[data-filter]").forEach(function (chip) {
    chip.addEventListener("click", function () {
      var f = chip.getAttribute("data-filter");
      document.querySelectorAll(".chip[data-filter]").forEach(function (c) { c.classList.toggle("on", c === chip); });
      document.querySelectorAll("[data-kinds]").forEach(function (card) {
        var kinds = card.getAttribute("data-kinds").split(" ");
        card.style.display = (f === "all" || kinds.indexOf(f) >= 0) ? "" : "none";
      });
    });
  });
})();
</script>
"""


def _brand() -> str:
    return ('<a class="brand" href="{root}index.html"><svg viewBox="0 0 32 32" aria-hidden="true">'
            '<circle cx="16" cy="16" r="13" fill="none" stroke="#1d4d43" stroke-width="1.6"/>'
            '<ellipse cx="16" cy="16" rx="5.4" ry="13" fill="none" stroke="#1d4d43" stroke-width="1"/>'
            '<path d="M3.5 16h25M5.5 10h21M5.5 22h21" stroke="#1d4d43" stroke-width="1"/>'
            '<circle cx="16" cy="16" r="2.4" fill="#c8873b"/></svg>'
            '<span>TerraKernel</span></a>')


def layout(data: SiteData, title: str, body: str, active: str = "", depth: int = 0, description: str = "") -> str:
    root = "../" * depth
    nav = [("overview", "index.html", "nav.overview"), ("steps", "index.html#steps", "nav.steps"),
           ("cases", "index.html#cases", "nav.cases"), ("repo", "repo.html", "nav.repo"),
           ("results", "results.html", "nav.results"), ("limits", "limits.html", "nav.limits")]
    links = "".join(
        f'<a href="{root}{href}" class="{"active" if key == active else ""}">{tw(label)}</a>'
        for key, href, label in nav)
    if data.site_config.get("gallery_href"):  # this site is one of several examples under a common entry page
        links = f'<a href="{root}{escape(data.site_config["gallery_href"])}">{tw("nav.gallery")}</a>' + links
    brand = _brand().replace("{root}", root)
    title_en = escape(title)
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title_en} · TerraKernel</title>
<meta name="description" content="{escape(description or data.goal[:160])}">
<link rel="stylesheet" href="{root}static/site.css">
</head><body>
<header class="site"><div class="wrap bar">{brand}
<nav class="main">{links}</nav>
<button class="lang" type="button">中文</button></div></header>
{body}
<footer class="site"><div class="wrap">
<span>{tw("footer.made")} · {escape(data.name)} · {escape(data.model)} · {escape(data.updated)}</span>
<span>{tw("common.served_offline") if False else ""}</span>
</div></footer>
{LANG_SCRIPT}
</body></html>"""


def gallery_page(entries: list[tuple[str, SiteData]]) -> str:
    """Entry page for several exported sites: one card per repository, linking to ``<dir>/index.html``."""
    cards = []
    for folder, data in entries:
        c = data.counts()
        graded = [r for r in data.runs if r.grade]
        facts = [(c["sources"], "stat.sources"), (c["objects"], "stat.objects"), (c["conflicts"], "stat.conflicts"),
                 (c["open_gaps"], "stat.gaps"), (c["verified_tools"], "stat.tools")]
        kv = "".join(f'<tr><th>{tw(label)}</th><td class="n">{n:,}</td></tr>' for n, label in facts)
        if graded:
            kv += f'<tr><th>{tw("gallery.runs")}</th><td class="n">{len(graded)}</td></tr>'
        kinds = sorted({s.kind.value if hasattr(s.kind, "value") else str(s.kind) for s in data.sources})
        tags = "".join(f'<span class="tag">{escape(k)}</span>' for k in kinds)
        cards.append(
            f'<a class="case" href="{escape(folder)}/index.html"><div class="tags">{tags}</div>'
            f'<h3>{bi(data.name, data.site_config.get("title_zh"))}</h3><p>{escape(data.goal[:280])}</p>'
            f'<table class="kv">{kv}</table><div class="from">{tw("gallery.open")} →</div></a>')
    brand = _brand().replace("{root}", "")
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>TerraKernel · examples</title>
<meta name="description" content="Research repositories compiled by TerraKernel from research materials.">
<link rel="stylesheet" href="static/site.css">
</head><body>
<header class="site"><div class="wrap bar">{brand}
<nav class="main"></nav>
<button class="lang" type="button">中文</button></div></header>
<main><section class="hero"><div class="wrap">
<div class="kicker">{tw("gallery.kicker")}</div>
<h1 style="max-width:22ch">{tw("gallery.title")}</h1>
<p class="lede" style="max-width:66ch">{tw("gallery.lede")}</p></div></section>
<section class="block"><div class="wrap"><div class="cases">{"".join(cards)}</div></div></section></main>
<footer class="site"><div class="wrap"><span>TerraKernel</span><span></span></div></footer>
{LANG_SCRIPT}
</body></html>"""


def _badge(text: str, cls: str = "") -> str:
    return f'<span class="status {cls}">{escape(text)}</span>'


def stat_block(data: SiteData) -> str:
    c = data.counts()
    cells = [
        (c["sources"], "stat.sources"), (c["evidence"], "stat.evidence"), (c["objects"], "stat.objects"),
        (c["conflicts"], "stat.conflicts"), (c["open_gaps"], "stat.gaps"),
        (c["verified_tools"], "stat.tools"), (c["skills"], "stat.skills"), (c["checks_pass"], "stat.checks"),
    ]
    out = ['<div class="stats-band"><div class="wrap"><div class="stats">']
    for n, label in cells:
        out.append(f'<div class="stat"><div class="n">{n:,}</div><div class="l">{tw(label)}</div></div>')
    out.append("</div></div></div>")
    return "".join(out)


def hero_flow(data: SiteData) -> str:
    """The compiled pipeline for this repository as a compact table."""
    c = data.counts()
    tools = data.tools()
    rows = [
        ("materials", f'{c["sources"]} files in <code>sources/</code>', f'{c["evidence"]} evidence'),
        ("evidence", "pages, lines, columns, functions", f'{c["objects"]} objects'),
        ("knowledge", f'{c["conflicts"]} conflicts · {c["answered_gaps"]} answered · {c["open_gaps"]} open',
         f'{c["docs"] + c["computations"]} docs'),
        ("tools", f'{c["verified_tools"]} verified · {c["tested_tools"]} property-tested · {c["failed_tools"]} withheld',
         f'{len(tools)} tools'),
        ("repository", f'{c["skills"]} skill(s) · AGENTS.md · MCP', f'{c["checks_pass"]} checks'),
    ]
    out = ['<div class="flow" role="table">']
    for k, v, n in rows:
        out.append(f'<div class="row" role="row"><div class="k">{escape(k)}</div><div class="v">{v}</div>'
                   f'<div class="n">{escape(n)}</div></div>')
    out.append("</div>")
    return "".join(out)


# ----------------------------------------------------------------------------- cases
def build_cases(data: SiteData) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    obj = data.object

    def name(oid: str) -> str:
        o = obj(oid)
        return o.name if o else oid

    def ev_items(oids: list[str], limit: int = 6) -> list[dict[str, Any]]:
        out, seen = [], set()
        for oid in oids:
            for lk, ev in data.evidence_of(oid):
                if ev.id in seen:
                    continue
                seen.add(ev.id)
                src = data.source_of(ev.source_id)
                out.append({"evidence": ev, "quote": lk.quote, "source": src})
                if len(out) >= limit:
                    return out
        return out

    def run_summary(relevant_objects: set[str], relevant_tools: set[str]) -> list[dict[str, Any]]:
        rows = []
        groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for r in data.runs:
            if not r.grade:
                continue
            keys = {k for k in relevant_objects if k in json.dumps(r.data.get("answer", {}))}
            tool_hit = relevant_tools and r.data.get("used_repository_tools")
            if not keys and not tool_hit:
                continue
            groups.setdefault((r.data.get("task", ""), r.model, r.setting), []).append(r.data)
        for (_task, model, setting), rs in sorted(groups.items()):
            rows.append({"model": model, "setting": setting, "runs": len(rs),
                         "bad_values": sorted({w for r in rs for w in
                                               [k for k, v in (r["grade"] or {}).get("values", {}).items()
                                                if v.get("status") != "correct"]}),
                         "mistakes": sorted({m for r in rs for m in (r["grade"] or {}).get("mistakes", [])}),
                         "mean_tokens": int(sum(r["usage"]["input"] + r["usage"]["cache_read"]
                                                + r["usage"]["cache_write"] + r["usage"]["output"] for r in rs) / len(rs))})
        return rows

    # conflicts
    for i, rel in enumerate(data.conflicts()):
        rels = [rel] + [r for r in data.relations if r.type.value in ("variant_of", "applies_to")
                        and (r.src in (rel.src, rel.dst) or r.dst in (rel.src, rel.dst))]
        oids = [rel.src, rel.dst] + [r.dst if r.src in (rel.src, rel.dst) else r.src for r in rels]
        cases.append({
            "id": f"conflict-{i+1}", "kinds": ["conflict"],
            "title": f"{name(rel.src)} vs {name(rel.dst)}",
            "lede": rel.note,
            "evidence": ev_items(oids),
            "objects": [rel.src, rel.dst] + sorted({(r.dst if r.src in (rel.src, rel.dst) else r.src) for r in rels} - {rel.src, rel.dst}),
            "relations": rels,
            "artifacts": sorted({a.id for oid in oids for a in data.artifacts_using(oid)}),
            "runs": run_summary(set(oids), set()),
            "source_ids": sorted({e["source"].id for e in ev_items(oids) if e["source"]}),
        })
    # open gaps
    for i, g in enumerate(data.open_gaps()):
        oids = [g.subject_id] if g.subject_id else []
        cases.append({
            "id": f"gap-{i+1}", "kinds": ["gap", "blocking" if g.severity.value == "blocking" else "warning"],
            "title": (name(g.subject_id) + ": " if g.subject_id else "") + g.description.split(".")[0][:120],
            "lede": g.description + (f" Suggestion: {g.suggestion}" if g.suggestion else ""),
            "evidence": ev_items(oids), "objects": oids, "relations": [], "artifacts": sorted(
                {a.id for a in data.artifacts_using(oids[0])} if oids else []),
            "runs": run_summary(set(oids), set()), "source_ids": [s for s in [x["source"].id if x["source"] else None for x in ev_items(oids)] if s],
        })
    # answered by people
    for i, g in enumerate(data.answered_gaps()):
        answer_objs = [o for o in data.objects.values() if o.attributes.get("answers_gap") == g.id]
        oids = ([g.subject_id] if g.subject_id else []) + [o.id for o in answer_objs]
        cases.append({
            "id": f"answered-{i+1}", "kinds": ["answered"], "title": (name(g.subject_id) + ": " if g.subject_id else "") + g.resolution[:110],
            "lede": f"{g.description} — {g.resolution} ({g.resolved_by})",
            "evidence": ev_items([o.id for o in answer_objs] + oids), "objects": oids, "relations": [],
            "artifacts": sorted({a.id for oid in oids for a in data.artifacts_using(oid)}),
            "runs": run_summary(set(oids), set()), "source_ids": ["human_answers"],
        })
    # tools
    for t in data.tools():
        if t.get("status") not in ("verified", "tested", "failed"):
            continue
        oids = list(t.get("objects") or [])
        cases.append({
            "id": f"tool-{t['name']}", "kinds": ["tool", "failed" if t.get("status") == "failed" else "verified"],
            "title": f"{t['name']} · {t.get('status')}",
            "lede": t.get("description", ""),
            "evidence": ev_items(oids, limit=4), "objects": oids, "relations": [],
            "artifacts": [f"tool:{t['name']}", f"test:{t['name']}", f"computation:{t['name']}"],
            "tool": t, "runs": run_summary(set(oids), {t["name"]}), "source_ids": [],
        })
    # updates
    for u in data.updates[-2:]:
        if u.get("result"):
            continue
        changed = u.get("objects", {}).get("changed", [])
        oids = [c["id"] for c in changed] + list(u.get("objects", {}).get("added", []))
        title = "Materials changed: " + ", ".join(sorted({(data.source_of(x) or type("x", (), {"path": x})).path
                                                          for x in u.get("sources", {}).get("changed", [])})) if u.get("sources") else "Update"
        cases.append({
            "id": f"update-{len(cases)}", "kinds": ["update"], "title": title,
            "lede": (f"{len(changed)} knowledge object(s) changed, {len(u.get('objects', {}).get('added', []))} added; "
                     f"{(u.get('files') or {}).get('changed', []).__len__()} file(s) rebuilt."),
            "evidence": ev_items(oids, limit=4), "objects": oids, "relations": [],
            "artifacts": [a for a in (u.get("predicted_impact") or {})][:8], "update": u,
            "runs": [], "source_ids": list(u.get("sources", {}).get("changed", [])),
        })
    return cases


# ----------------------------------------------------------------------------- evidence rendering
def evidence_card(data: SiteData, site_dir: Path, item: dict[str, Any], depth: int = 0) -> str:
    ev, quote, src = item["evidence"], item["quote"], item["source"]
    root = "../" * depth
    loc = ev.locator.short() or ev.id
    path_label = src.path if src else ev.source_id
    media = ""
    file_path = None
    if src is not None:
        candidate = data.project.repo / "sources" / src.path
        file_path = candidate if candidate.exists() else data.project.source_file(src)
    if file_path and file_path.exists():
        suffix = file_path.suffix.lower()
        if suffix == ".pdf" and ev.locator.page:
            rel = A.pdf_region(data.project.repo, file_path, ev.locator.page, ev.locator.bbox, site_dir)
            if rel:
                media = f'<div class="media"><img loading="lazy" src="{root}{rel}" alt="{escape(loc)}"></div>'
        elif suffix in (".py", ".md", ".txt", ".toml", ".json", ".yaml", ".yml", ".r", ".jl", ".sql", ".sh", ".ipynb"):
            if ev.locator.line_start:
                media = f'<div class="media">{A.text_lines(file_path, ev.locator.line_start, ev.locator.line_end)}</div>'
        elif suffix in (".csv", ".tsv") and ev.locator.column:
            html, stats = A.table_preview(file_path, ev.locator.column)
            if html:
                media = f'<div class="media">{html}</div>'
        elif ev.asset:
            fig = A.figure_image(data.project.assets_dir, ev.asset, site_dir)
            if fig:
                media = f'<div class="media"><img loading="lazy" src="{root}{fig}" alt="figure"></div>'
    q = f'<blockquote class="quote">“{escape(quote or ev.content[:400])}”</blockquote>' if (quote or ev.content) else ""
    return (f'<figure class="ev-card"><div class="src"><span>{escape(path_label)}</span><span>{escape(loc)}</span></div>'
            f'{q}{media}<figcaption class="caption">{escape(ev.kind.value)} · {escape(ev.id)}</figcaption></figure>')


def object_block(data: SiteData, oid: str, depth: int = 0) -> str:
    o = data.object(oid)
    root = "../" * depth
    if o is None:
        return f'<div class="obj-block"><span class="id">{escape(oid)}</span></div>'
    basis = {"stated": "stated by the materials", "inferred": "derived from the materials",
             "measured": "measured from the data", "human_confirmed": "confirmed by a person"}.get(o.basis.value, o.basis.value)
    rows = [["basis", basis]]
    for k, v in o.attributes.items():
        if k in ("members", "answers_gap"):
            continue
        text = json.dumps(v, ensure_ascii=False, default=str) if isinstance(v, (dict, list)) else str(v)
        if len(text) > 600:
            text = text[:600] + "..."
        rows.append([k, text])
    table = '<table class="kv">' + "".join(f"<tr><th>{escape(str(k))}</th><td>{escape(str(v))}</td></tr>"
                                         for k, v in rows if not isinstance(v, (dict, list))) + "</table>"
    note = f'<div class="small">{escape(o.basis_note)}</div>' if o.basis_note else ""
    status = _badge(o.status.value) if o.status.value != "active" else ""
    docs = [a for a in data.artifacts_using(o.id) if a.kind in ("knowledge_doc", "computation_doc")]
    doc_links = "".join(f'<a class="small" style="margin-right:10px" href="{root}docs/{_slug(a.path)}.html">'
                        f'{escape(a.path.removeprefix("knowledge/"))}</a>' for a in docs[:3])
    return (f'<div class="obj-block"><div class="id">{escape(o.id)}</div>'
            f'<div class="name"><a href="{root}objects/{_slug(o.id)}.html" style="border:0">{escape(o.name)}</a> '
            f'{_badge(o.type.value)} {status}</div>'
            f'<div class="sum">{escape(o.summary)}</div>{note}{table}'
            + (f'<div style="margin-top:6px">{doc_links}</div>' if doc_links else "") + "</div>")


def _slug(text: str) -> str:
    import re

    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()[:80]


def artifact_block(data: SiteData, aid: str, depth: int = 0) -> str:
    a = data.spec.artifact(aid)
    root = "../" * depth
    if a is None:
        return ""
    doc_link = ""
    if a.kind in ("knowledge_doc", "computation_doc"):
        doc_link = f' <a href="{root}docs/{_slug(a.path)}.html">{tw("common.read_more")}</a>'
    reuse = ""
    entry = data.tool_entry(a.id.removeprefix("tool:")) if a.kind == "tool" else None
    if entry:
        cases_n = entry.get("reference_cases", 0)
        tests = entry.get("tests") or {}
        reuse = (f'<div class="small">{tw("repo.status")}: {_badge(entry.get("status", ""), entry.get("status", ""))} · '
                 f'{tests.get("passed", 0)} tests passed · {cases_n} reference case(s) quoted from the materials'
                 + (f' · reuses <code>{escape(entry["reuse"]["symbol"])}</code> from <code>{escape(entry["reuse"]["source"])}</code>'
                    if entry.get("reuse") else "") + "</div>")
    return (f'<div class="obj-block"><div class="name"><a href="{root}files/{_slug(a.path)}.html" style="border:0">'
            f'{escape(a.path)}</a>{doc_link}</div><div class="small">{escape(a.kind)} · {escape(a.title)}</div>'
            f'<div class="sum">{escape(a.description)}</div>{reuse}</div>')


def run_rows_html(data: SiteData, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return f'<p class="small">{tw("cases.none")}</p>'
    body = []
    for r in rows:
        bad = r["bad_values"]
        cls = "ok" if not bad and not r["mistakes"] else ("bad" if bad else "mid")
        label = "all correct" if not bad and not r["mistakes"] else (", ".join(bad) or ", ".join(r["mistakes"]))
        body.append(f'<tr><td class="mono">{escape(r["model"].replace("claude-", ""))} · {escape(r["setting"])}</td>'
                    f'<td class="n">{r["runs"]}</td><td><span class="pill {cls}">{escape(label)}</span></td>'
                    f'<td class="mono">{r["mean_tokens"]:,}</td></tr>')
    return ('<table><thead><tr><th>' + tw("results.table") + '</th><th>' + tw("results.runs") +
            '</th><th>' + tw("results.correct") + '</th><th>' + tw("results.tokens") + '</th></tr></thead><tbody>'
            + "".join(body) + "</tbody></table>")


def case_page(data: SiteData, case: dict[str, Any], site_dir: Path) -> str:
    objects = case.get("objects", [])
    ev_html = "".join(evidence_card(data, site_dir, e, depth=1) for e in case["evidence"]) or \
        '<p class="small">—</p>'
    rel_html = ""
    for r in case.get("relations", []):
        if r.type.value in ("variant_of", "applies_to"):
            rel_html += (f'<div class="small">{escape(r.type.value)}: {escape(r.src)} → {escape(r.dst)}'
                         f'{" — " + escape(r.note[:200]) if r.note else ""}</div>')
    obj_html = "".join(object_block(data, oid, depth=1) for oid in objects) or '<p class="small">—</p>'
    art_html = "".join(artifact_block(data, aid, depth=1) for aid in case.get("artifacts", [])[:12])
    tool = case.get("tool")
    if tool:
        tests = tool.get("tests") or {}
        cases = tool.get("reference_cases", 0)
        art_html += (f'<table class="kv"><tr><th>strategy</th><td>{escape(tool.get("strategy", ""))}</td></tr>'
                     f'<tr><th>tests</th><td>{tests.get("passed", 0)} passed, {tests.get("failed", 0)} failed</td></tr>'
                     f'<tr><th>reference cases</th><td>{cases} quoted from the materials</td></tr>'
                     + (f'<tr><th>reuses</th><td><code>{escape(tool["reuse"]["symbol"])}</code> from '
                        f'<code>{escape(tool["reuse"]["source"])}</code></td></tr>' if tool.get("reuse") else "")
                     + "</table>")
    update = case.get("update")
    if update:
        files = update.get("files") or {}
        art_html += (f'<div class="small">{len(files.get("changed", []))} files rebuilt, '
                     f'{len(files.get("added", []))} added, {len(files.get("removed", []))} removed.</div>'
                     '<div class="lines">' + "".join(f'<div class="ln"><span class="tx">{escape(f)}</span></div>'
                                                     for f in files.get("changed", [])[:20]) + "</div>")
    tags = "".join(f'<span class="tag {escape(k)}">{escape(k)}</span>' for k in case["kinds"])
    body = f"""
<main>
<div class="wrap case-head">{tags}<h1 style="margin-top:16px">{escape(case["title"])}</h1>
<p class="lede">{escape(case["lede"])}</p>
<p class="small"><a href="../index.html#cases">← {tw("nav.cases")}</a></p></div>
<div class="wrap"><div class="case-grid">
<section class="case-part"><h2>{tw("cases.source")}</h2>{ev_html}</section>
<section class="case-part"><h2>{tw("cases.knowledge")}</h2>{obj_html}{rel_html}</section>
<section class="case-part"><h2>{tw("cases.became")}</h2>{art_html or '<p class="small">—</p>'}</section>
<section class="case-part"><h2>{tw("cases.agent")}</h2>{run_rows_html(data, case.get("runs", []))}</section>
</div></div></main>"""
    return layout(data, case["title"], body, active="cases", depth=1, description=case["lede"])


# ----------------------------------------------------------------------------- index
def index_page(data: SiteData, cases: list[dict[str, Any]], site_dir: Path) -> str:
    c = data.counts()
    kinds_present = sorted({k for case in cases for k in case["kinds"] if k in
                            ("conflict", "gap", "answered", "tool", "update")})
    chips = [f'<button class="chip on" data-filter="all">{tw("cases.all")}<span class="c">{len(cases)}</span></button>']
    for k in kinds_present:
        n = sum(k in case["kinds"] for case in cases)
        chips.append(f'<button class="chip" data-filter="{k}"><span class="i18n" data-en="{k}" data-zh="{ {"conflict":"冲突","gap":"待确认","answered":"人工回答","tool":"工具","update":"更新"}[k] }">{k}</span><span class="c">{n}</span></button>')
    card_html = []
    for case in cases:
        tags = "".join(f'<span class="tag {escape(k)}">{escape(k)}</span>' for k in case["kinds"])
        srcs = ", ".join(sorted({(data.source_of(s) or type("x", (), {"path": s})).path for s in case.get("source_ids", [])}))[:90]
        card_html.append(
            f'<a class="case" data-kinds="{" ".join(case["kinds"])}" href="cases/{case["id"]}.html">'
            f'<div class="tags">{tags}</div><h3>{escape(case["title"])}</h3>'
            f'<p>{escape(case["lede"][:240])}</p><div class="from">{escape(srcs)}</div></a>')

    type_order = ["concept", "claim", "method", "dataset", "constraint", "capability"]
    types_html = charts.type_distribution(c["objects_by_type"], type_order)
    hero_h1 = (data.site_config.get("hero_title") or data.name.replace("-", " ")).strip()
    events = [e for e in data.events if e.get("kind") in ("item", "warning", "error", "stage_end")]
    last_build = [e for e in events if e.get("stage") == "compile" or e.get("stage") == "validate"][-8:]
    replay = "".join(
        f'<div class="step-run{" on" if i == 0 else ""}"><div class="no">{escape(e.get("at", "")[11:19])} · '
        f'{escape(e.get("stage", ""))}</div><div class="tool">{escape(e.get("message", "")[:300])}</div></div>'
        for i, e in enumerate(last_build))
    steps = "".join(f'<div class="step"><div class="t">{tw(f"steps.{i}.t")}</div><div class="d">{tw(f"steps.{i}.d")}</div></div>'
                    for i in range(1, 5))
    body = f"""
<main>
<section class="hero"><div class="wrap"><div class="grid">
<div><div class="kicker">{tw("hero.kicker")} · {bi(data.name, data.site_config.get("title_zh"))}</div>
<h1>{bi(hero_h1, data.site_config.get("hero_title_zh"))}</h1>
<p class="lede">{tw("hero.lede")}</p>
<div class="cta"><a class="btn" href="#cases">{tw("hero.goto")}</a>
<a class="btn ghost" href="repo.html">{tw("hero.repo")}</a></div></div>
<div><p class="goal">{escape(data.goal)}</p>{hero_flow(data)}</div>
</div></div></section>
{stat_block(data)}
<section class="block" id="steps"><div class="wrap"><div class="head"><h2>{tw("steps.title")}</h2>
<div class="intro">{types_html}</div></div><div class="steps">{steps}</div>
<div class="replay" style="margin-top:34px"><div class="bar"><button data-play="build-replay">▶ {tw("common.play")}</button>
<span class="small">{tw("nav.steps")} · {escape(str(len(last_build)))} events</span></div>
<div class="steps" id="build-replay">{replay}</div></div>
</div></section>
<section class="block" id="cases"><div class="wrap"><div class="head"><h2>{tw("cases.title")}</h2>
<div class="intro">{tw("cases.intro")}</div></div>
<div class="filters">{"".join(chips)}</div>
<div class="cases">{"".join(card_html)}</div></div></section>
</main>"""
    return layout(data, data.name, body, active="overview", description=data.goal[:200])


# ----------------------------------------------------------------------------- repo
def repo_page(data: SiteData) -> str:
    artifacts = data.spec.artifacts
    kinds = {}
    for a in artifacts:
        kinds.setdefault(a.kind, []).append(a)
    rows = []
    for kind in ("config", "runtime", "tool", "test", "computation_doc", "knowledge_doc", "skill", "entry", "adapter", "source"):
        for a in kinds.get(kind, []):
            rows.append(f'<tr><td class="mono"><a href="files/{_slug(a.path)}.html">{escape(a.path)}</a></td>'
                        f'<td>{escape(kind)}</td><td>{_badge(a.status, a.status)}</td>'
                        f'<td class="mono small">{len(a.objects)}</td>'
                        f'<td class="small">{escape(", ".join(a.depends_on[:3]))}{"…" if len(a.depends_on) > 3 else ""}</td></tr>')
    nodes = [{"id": a.id, "kind": a.kind, "status": a.status, "label": a.path.split("/")[-1] or a.id} for a in artifacts
             if a.kind not in ("source",)]
    known = {n["id"] for n in nodes}
    edges = [(a.id, d) for a in artifacts for d in a.depends_on if a.id in known and d in known]
    graph = charts.dependency_graph(nodes, edges, set())
    tools_html = []
    for t in data.tools():
        tests = t.get("tests") or {}
        tools_html.append(
            f'<div class="obj-block"><div class="name">{escape(t["name"])} {_badge(t.get("status", ""), t.get("status", ""))}</div>'
            f'<div class="sum">{escape(t.get("description", ""))}</div>'
            f'<div class="small">{escape(t.get("strategy", ""))} · {tests.get("passed", 0)} tests passed · '
            f'{t.get("reference_cases", 0)} reference case(s) · output {escape(str(t.get("output_unit") or "—"))}</div></div>')
    body = f"""
<main><div class="wrap" style="padding-top:46px"><h1 style="font-size:2.4rem">{tw("repo.title")}</h1>
<p class="lede" style="max-width:64ch">{tw("repo.intro")}</p>
<p><a class="btn" href="download/repo.zip">{tw("repo.download")}</a>
<a class="btn ghost" href="files/agents-md.html">AGENTS.md</a></p></div>
<section class="block"><div class="wrap"><h2>{tw("repo.artifacts")}</h2>
<table><thead><tr><th>{tw("repo.file")}</th><th>{tw("repo.kind")}</th><th>{tw("repo.status")}</th>
<th>{tw("repo.objects")}</th><th>{tw("repo.depends")}</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div></section>
<section class="block"><div class="wrap"><h2>{tw("repo.deps")}</h2>{graph}</div></section>
<section class="block"><div class="wrap"><h2>{tw("repo.tools")}</h2>{"".join(tools_html)}</div></section>
</main>"""
    return layout(data, data.spec.summary or data.name, body, active="repo", description=data.spec.summary)


# ----------------------------------------------------------------------------- results
def results_page(data: SiteData) -> str:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for r in data.runs:
        if r.grade:
            groups.setdefault((r.data.get("task", ""), r.model, r.setting), []).append(r.data)
    chart_groups = []
    rows = []
    for (task, model, setting), rs in sorted(groups.items()):
        all_ok = sum(bool(r["grade"].get("all_correct")) for r in rs)
        tokens = int(sum(r["usage"]["input"] + r["usage"]["cache_read"] + r["usage"]["cache_write"] + r["usage"]["output"]
                         for r in rs) / len(rs))
        cost = sum(r["usage"]["cost_usd"] for r in rs) / len(rs)
        steps = sum(r["steps"] for r in rs) / len(rs)
        chart_groups.append({"model": model, "setting": setting, "all_correct": all_ok, "runs": len(rs),
                             "mean_tokens": tokens})
        rows.append(f'<tr><td>{escape(task)}</td><td class="mono">{escape(model.replace("claude-", ""))}</td>'
                    f'<td>{escape(setting)}</td><td class="n">{len(rs)}</td>'
                    f'<td><span class="pill {"ok" if all_ok == len(rs) else "mid"}">{all_ok}/{len(rs)}</span></td>'
                    f'<td class="n">{tokens:,}</td><td class="n">{steps:.1f}</td><td class="n">${cost:.3f}</td>'
                    f'<td><a href="runs/{_slug(rs[0]["run_id"])}.html">{tw("common.replay")}</a></td></tr>')
    build_cost = data.project.total_model_cost()["cost_usd_estimate"]
    body = f"""
<main><div class="wrap" style="padding-top:46px"><h1 style="font-size:2.4rem">{tw("results.title")}</h1>
<p class="lede" style="max-width:66ch">{tw("results.intro")}</p></div>
<section class="block"><div class="wrap">
{charts.eval_chart(chart_groups) if chart_groups else '<p class="small">No graded runs yet.</p>'}
<div class="table-wrap" style="margin-top:26px"><table class="result-table"><thead><tr><th>Task</th><th>Model</th><th>Setting</th>
<th>{tw("results.table")}</th><th>{tw("results.correct")}</th><th>{tw("results.tokens")}</th><th>Steps</th>
<th>{tw("results.cost")}</th><th></th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>
<p class="small">{tw("results.build")}: ${build_cost:.2f} (estimate, official list prices).</p>
<p class="intro" style="margin-top:22px">{tw("results.note")}</p>
</div></section></main>"""
    return layout(data, "Results", body, active="results")


# ----------------------------------------------------------------------------- limits
def limits_page(data: SiteData) -> str:
    c = data.counts()
    tool_lines = []
    for t in data.tools():
        tool_lines.append(f'<tr><td class="mono">{escape(t["name"])}</td><td>{_badge(t.get("status", ""), t.get("status", ""))}</td>'
                          f'<td>{t.get("reference_cases", 0)}</td><td class="small">{escape("; ".join(t.get("problems", [])[:2]))}</td></tr>')
    sources = []
    for s in data.sources:
        if s.id == "human_answers":
            sources.append(f'<li><code>{escape(s.path)}</code> — answers recorded by people in this build '
                           f'(represented as <code>human:</code> actors).</li>')
        else:
            sources.append(f'<li><code>{escape(s.path)}</code> — {escape(s.kind.value)}, {s.size:,} bytes, '
                           f'sha256 {escape(s.sha256[:12])}…</li>')
    answered = data.answered_gaps()
    answered_html = "".join(f"<li>{escape(g.description)} → <em>{escape(g.resolution or '')}</em> "
                            f"({escape(g.resolved_by or '')})</li>" for g in answered) or "<li>—</li>"
    body = f"""
<main><div class="wrap" style="padding-top:46px"><h1 style="font-size:2.4rem">{tw("limits.title")}</h1></div>
<section class="block"><div class="wrap"><div class="repo-grid">
<div><h2>{tw("limits.claims")}</h2><ul>
<li>Every knowledge object cites evidence in the materials with a verbatim quote, checked by matching the quote against the cited unit.</li>
<li>Conflicts are kept as separate definitions; {c["conflicts"]} conflict(s) are recorded and none was merged away.</li>
<li>{c["gaps"]} questions the materials leave open were recorded ({c["answered_gaps"]} answered by people); no default was invented for the rest.</li>
<li>{c["verified_tools"]} tool(s) verified against values quoted from the materials, {c["tested_tools"]} tested for properties only, {c["failed_tools"]} failed and are withheld from agents.</li>
<li>The generated repository passes {c["checks_pass"]} structural checks ({c["checks_fail"]} failed).</li>
</ul></div>
<div><h2>{tw("limits.nonclaims")}</h2><ul>
<li>Passing structural checks does not mean the research conclusions are correct; it means the repository is well-formed, traceable and its tools pass their tests.</li>
<li>Quotes are checked for presence in the evidence, not for interpreting it correctly; interpretation is reviewed only by the human answers shown below.</li>
<li>Values measured from data (profiles, statistics) describe the files as delivered; they say nothing about the validity of the measurements.</li>
<li>The demo materials are synthetically generated for testing and are labelled as such in their own text.</li>
</ul></div></div></div></section>
<section class="block"><div class="wrap"><h2>{tw("limits.units_t")}</h2>
<table><thead><tr><th>Tool</th><th>Status</th><th>Reference cases</th><th>Notes</th></tr></thead>
<tbody>{"".join(tool_lines)}</tbody></table></div></section>
<section class="block"><div class="wrap"><h2>Answered by people</h2><ul>{answered_html}</ul></div></section>
<section class="block"><div class="wrap"><h2>{tw("limits.sources")}</h2><ul>{"".join(sources)}</ul>
<p class="small">Interface fonts: IBM Plex, SIL Open Font License 1.1 (self-hosted, <code>static/fonts/IBM-Plex-LICENSE.txt</code>).</p>
</div></section></main>"""
    return layout(data, "Evidence and limits", body, active="limits")


# ----------------------------------------------------------------------------- knowledge docs / objects / files / runs
def doc_page(data: SiteData, doc: dict[str, Any]) -> str:
    fm = doc["frontmatter"]
    oids = doc.get("objects") or []
    oid_to_page = {oid: f"../objects/{_slug(oid)}.html" for oid in data.objects}
    key_to_oid = {str(src.get("id")): str(src.get("object")) for src in (fm.get("sources") or [])
                  if isinstance(src, dict) and src.get("object")}

    def href(label: str) -> str | None:
        return oid_to_page.get(key_to_oid.get(label, label))

    html = md_to_html(doc["body"], object_href=href, base_href="../")
    aside = [f'<h3>{tw("kdoc.objects")}</h3>']
    for oid in oids:
        o = data.object(oid)
        if o:
            aside.append(f'<div class="small" style="margin-bottom:10px"><a href="../objects/{_slug(oid)}.html">'
                         f'{escape(o.name)}</a><br><span class="mono" style="font-size:.7rem">{escape(oid)}</span></div>')
    meta = ['<h3>OKF</h3><table class="kv">']
    for k in ("type", "status", "description"):
        if fm.get(k):
            meta.append(f"<tr><th>{k}</th><td>{escape(str(fm[k])[:300])}</td></tr>")
    ver = fm.get("verified")
    if ver:
        items = ver if isinstance(ver, list) else [ver]
        meta.append(f"<tr><th>verified</th><td>{len(items)} record(s)</td></tr>")
    meta.append(f"<tr><th>sources</th><td>{len(fm.get('sources') or [])}</td></tr></table>")
    body = f"""
<main><div class="wrap"><div class="doc-layout"><article class="doc-body">{html}</article>
<aside class="meta"><p class="small"><a href="../index.html">← {tw("kdoc.back")}</a></p>{"".join(meta)}{"".join(aside)}</aside>
</div></div></main>"""
    return layout(data, doc["title"], body, depth=1, description=fm.get("description", ""))


def object_page(data: SiteData, oid: str, site_dir: Path) -> str:
    blocks = [object_block(data, oid)]
    evs = data.evidence_of(oid)
    rels = data.relations_of(oid)
    rel_html = "".join(
        f'<tr><td>{escape(r.type.value)}</td><td class="mono small">'
        f'<a href="{_slug(r.src)}.html">{escape(r.src)}</a></td><td class="mono small">'
        f'<a href="{_slug(r.dst)}.html">{escape(r.dst)}</a></td><td class="small">{escape(r.note[:240])}</td></tr>'
        for r in rels)
    arts = data.artifacts_using(oid)
    body = f"""
<main><div class="wrap" style="padding-top:36px">
<p class="small"><a href="../index.html">← {tw("kdoc.back")}</a></p>
<h2 style="font-family:var(--mono);font-size:1rem;color:var(--muted);font-weight:400">{escape(oid)}</h2>
{blocks[0]}
<h2 style="margin-top:34px;font-size:1.1rem">{tw("obj.evidence")}</h2>
{''.join(evidence_card(data, site_dir, {"evidence": ev, "quote": lk.quote, "source": data.source_of(ev.source_id)}, depth=1) for lk, ev in evs) or '<p class="small">—</p>'}
<h2 style="margin-top:34px;font-size:1.1rem">{tw("obj.relations")}</h2>
{'<table><thead><tr><th>type</th><th>from</th><th>to</th><th>note</th></tr></thead><tbody>' + rel_html + '</tbody></table>' if rel_html else '<p class="small">—</p>'}
<h2 style="margin-top:34px;font-size:1.1rem">{tw("obj.usedby")}</h2>
<table><tbody>{''.join(f'<tr><td class="mono">{escape(a.path)}</td><td>{escape(a.kind)}</td><td>{_badge(a.status, a.status)}</td></tr>' for a in arts)}</tbody></table>
</div></main>"""
    o = data.object(oid)
    return layout(data, o.name if o else oid, body, depth=1, description=(o.summary if o else ""))


def file_page(data: SiteData, path: str) -> str:
    root = data.project.repo
    f = root / path
    if f.suffix == ".md":
        text = f.read_text(encoding="utf-8")
        fm, body_md = split_frontmatter(text)
        content = md_to_html(body_md, base_href="../")
        if fm:
            content = '<table class="kv">' + "".join(
                f"<tr><th>{escape(k)}</th><td>{escape(str(v)[:500])}</td></tr>" for k, v in fm.items()) + "</table>" + content
    else:
        from terrakernel.site.render import _highlight_code

        lang = {".py": "python", ".json": "json", ".toml": "toml", ".yaml": "yaml", ".yml": "yaml", ".csv": "text"}.get(
            f.suffix.lower(), "")
        content = _highlight_code(f.read_text(encoding="utf-8", errors="replace"), lang)
    body = f"""
<main><div class="wrap" style="padding-top:36px"><p class="small"><a href="../repo.html">← {tw("nav.repo")}</a></p>
<h2 style="font-family:var(--mono);font-size:1rem;color:var(--muted);font-weight:400">{escape(path)}</h2>
{content}</div></main>"""
    return layout(data, path, body, depth=1)


def run_page(data: SiteData, run: dict[str, Any]) -> str:
    steps = run.get("trace", [])
    out = []
    for s in steps:
        calls = "".join(
            f'<div class="tool">{escape(c["name"])} <code>{escape(json.dumps(c["input"], ensure_ascii=False)[:400])}</code></div>'
            for c in s.get("tool_calls", []))
        results = "".join(f'<pre>{escape(r["output"][:1600])}</pre>' for r in s.get("results", []))
        text = f'<div class="small">{escape(s.get("text", "")[:600])}</div>' if s.get("text") else ""
        out.append(f'<div class="step-run"><div class="no">{tw("run.steps")} {s["step"]} · '
                   f'{escape(str(s.get("stop_reason")))}</div>{text}{calls}{results}</div>')
    grade = run.get("grade") or {}
    grade_rows = "".join(
        f'<tr><td class="mono">{escape(k)}</td><td class="n">{escape(str(v.get("got")))}</td>'
        f'<td class="n">{escape(str(v.get("expected")))}</td>'
        f'<td><span class="pill {"ok" if v.get("status") == "correct" else "bad"}">{escape(v.get("status", ""))}</span></td></tr>'
        for k, v in (grade.get("values") or {}).items())
    answer = run.get("answer") or {}
    body = f"""
<main><div class="wrap" style="padding-top:36px">
<p class="small"><a href="../results.html">← {tw("nav.results")}</a></p>
<h2 style="font-size:1.6rem">{escape(run.get("task", ""))} · {escape(run.get("setting", ""))} · {escape(run.get("model", "").replace("claude-", ""))}</h2>
<p class="small">{escape(run.get("status", ""))} · {run.get("steps", 0)} steps · {run.get("seconds", 0)} s ·
{run.get("usage", {}).get("output", 0):,} output tokens · ${run.get("usage", {}).get("cost_usd", 0):.4f}</p>
<div class="replay"><div class="bar"><button data-play="run-{_slug(run.get("run_id", "x"))}">▶ {tw("common.play")}</button>
<span class="small">{tw("run.steps")} {len(steps)}</span></div>
<div class="steps" id="run-{_slug(run.get("run_id", "x"))}">{"".join(out)}</div></div>
<h3 style="margin-top:30px">{tw("run.grade")}</h3>
<table><thead><tr><th>value</th><th>got</th><th>expected</th><th>status</th></tr></thead><tbody>{grade_rows}</tbody></table>
<h3 style="margin-top:26px">{tw("run.answer")}</h3>
<p>{escape((answer.get("summary") or "")[:1500])}</p>
<ul>{''.join(f'<li>{escape(t)}</li>' for t in (answer.get("transformations") or [])[:12])}</ul>
<div class="small">{tw("common.open")}: {'; '.join(escape(i) for i in (answer.get("open_issues") or [])[:8])}</div>
</div></main>"""
    return layout(data, f"{run.get('task')} · {run.get('setting')}", body, depth=1, description="agent run replay")
