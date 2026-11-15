"""Inline SVG charts for the site (no JavaScript charting library, no external hosts)."""

from __future__ import annotations

from html import escape
from typing import Any

PALETTE = {
    "pine": "#1d4d43", "pine_2": "#2f6d5f", "ink": "#1f2421", "muted": "#6b746e", "line": "#dfe3dc",
    "paper": "#fcfcf8", "soft": "#f1f3ee", "amber": "#c8873b", "red": "#a33b26", "blue": "#3d5a80",
    "green": "#4f7d4a", "grey": "#9aa39b",
}


def _fmt(n: float) -> str:
    if n >= 1000:
        return f"{n/1000:.1f}k"
    if n >= 100:
        return f"{n:.0f}"
    return f"{n:g}"


def stacked_bar(parts: list[tuple[str, float, str]], width: int = 360, height: int = 16, label: str = "") -> str:
    total = sum(max(0.0, v) for _, v, _ in parts) or 1.0
    x = 0.0
    rects = []
    for name, value, colour in parts:
        w = max(0.0, value) / total * width
        if w > 0:
            rects.append(f'<rect x="{x:.2f}" y="0" width="{w:.2f}" height="{height}" fill="{colour}">'
                         f"<title>{escape(name)}: {_fmt(value)}</title></rect>")
            x += w
    return (f'<svg class="bar" viewBox="0 0 {width} {height}" preserveAspectRatio="none" role="img" '
            f'aria-label="{escape(label)}">{"".join(rects)}</svg>')


def type_distribution(counts: dict[str, int], order: list[str] | None = None, labels: dict[str, str] | None = None) -> str:
    """Stacked bar of knowledge objects by type, with a legend carrying the counts."""
    order = order or list(counts)
    colours = [PALETTE["pine"], PALETTE["pine_2"], PALETTE["blue"], PALETTE["amber"], PALETTE["green"],
               PALETTE["grey"]]
    parts = [(k, counts.get(k, 0), colours[i % len(colours)]) for i, k in enumerate(order) if counts.get(k, 0)]
    legend = "".join(f'<span><i style="background:{c}"></i>{(labels or {}).get(k, escape(k))} {v}</span>'
                     for k, v, c in parts)
    return stacked_bar(parts, label="knowledge objects by type") + f'<div class="legend">{legend}</div>'


def mini_hist(values: list[float], width: int = 220, height: int = 46, colour: str = PALETTE["pine"]) -> str:
    if not values:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    step = width / max(1, len(values))
    pts = " ".join(f"{i * step + step / 2:.1f},{height - 3 - (v - lo) / span * (height - 6):.1f}"
                   for i, v in enumerate(values))
    return (f'<svg class="spark" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img">'
            f'<polyline points="{pts}" fill="none" stroke="{colour}" stroke-width="1.4"/></svg>')


def eval_chart(groups: list[dict[str, Any]], width: int = 560) -> str:
    """One row per (task, model, setting): correct fraction as a dot, token cost as a bar."""
    row_h, gap = 26, 14
    height = max(1, len(groups)) * (row_h + gap) + 30
    left, right = 150, width - 120
    out = [f'<svg class="eval" viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="agent results">']
    for i, g in enumerate(groups):
        y = 8 + i * (row_h + gap)
        label = f"{g['model'].replace('claude-', '')} · {g['setting']}"
        out.append(f'<text x="0" y="{y + 13}" class="lbl">{escape(label)}</text>')
        frac = (g.get("all_correct") or 0) / max(1, g.get("runs") or 1)
        out.append(f'<rect x="{left}" y="{y + 2}" width="{right - left}" height="14" fill="{PALETTE["soft"]}"/>')
        out.append(f'<rect x="{left}" y="{y + 2}" width="{(right - left) * frac:.1f}" height="14" '
                   f'fill="{PALETTE["pine"] if frac == 1 else PALETTE["amber"]}"/>')
        out.append(f'<text x="{right + 8}" y="{y + 13}" class="val">{frac * 100:.0f}% · '
                   f'{_fmt(g.get("mean_tokens") or 0)} tok</text>')
    out.append(f'<text x="{left}" y="{height - 2}" class="axis">bar = fraction of runs with every value correct · '
               f'right label = tokens per run</text>')
    out.append("</svg>")
    return "".join(out)


def dependency_graph(nodes: list[dict[str, Any]], edges: list[tuple[str, str]], highlight: set[str],
                     width: int = 880) -> str:
    """Layered graph: columns by kind, edges as curves; highlight marks impacted artifacts."""
    order = ["config", "runtime", "tool", "test", "computation_doc", "knowledge_doc", "skill", "entry", "adapter"]
    layers: dict[str, list[dict[str, Any]]] = {}
    for n in nodes:
        layers.setdefault(n["kind"], []).append(n)
    cols = [k for k in order if layers.get(k)]
    if not cols:
        return ""
    col_w = width / max(1, len(cols))
    max_rows = max(len(layers[k]) for k in cols)
    box_h, pad = 18, 8
    height = max_rows * (box_h + pad) + 30
    pos: dict[str, tuple[float, float]] = {}
    for ci, kind in enumerate(cols):
        items = sorted(layers[kind], key=lambda n: n["id"])
        for ri, n in enumerate(items):
            pos[n["id"]] = (ci * col_w + 6, 18 + ri * (box_h + pad))
    out = [f'<svg class="dep" viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="dependencies">']
    for src, dst in edges:
        if src not in pos or dst not in pos:
            continue
        x1, y1 = pos[src]
        x2, y2 = pos[dst]
        x1 += 118
        y1 += box_h / 2
        y2 += box_h / 2
        colour = PALETTE["amber"] if (src in highlight or dst in highlight) else PALETTE["line"]
        out.append(f'<path d="M{x1:.0f},{y1:.0f} C{x1 + 30:.0f},{y1:.0f} {x2 - 30:.0f},{y2:.0f} {x2:.0f},{y2:.0f}" '
                   f'fill="none" stroke="{colour}" stroke-width="1"/>')
    for ci, kind in enumerate(cols):
        out.append(f'<text x="{ci * col_w + 6}" y="10" class="axis">{escape(kind.replace("_", " "))}</text>')
    status_colour = {"verified": PALETTE["green"], "generated": PALETTE["pine_2"], "failed": PALETTE["red"],
                     "candidate": PALETTE["amber"], "blocked": PALETTE["amber"], "planned": PALETTE["grey"]}
    for n in nodes:
        x, y = pos[n["id"]]
        fill = PALETTE["amber"] if n["id"] in highlight else status_colour.get(n.get("status", ""), PALETTE["grey"])
        out.append(f'<rect x="{x}" y="{y}" width="118" height="{box_h}" rx="2" fill="{fill}" opacity="0.14" '
                   f'stroke="{fill}" stroke-width="1"/>')
        label = n.get("label") or n["id"]
        out.append(f'<text x="{x + 5}" y="{y + 12}" class="node" fill="{PALETTE["ink"]}">{escape(label[:22])}</text>')
    out.append("</svg>")
    return "".join(out)
