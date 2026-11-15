"""Code ingest.

Python files and notebooks are parsed with ``ast``: one evidence unit per top-level
function/class (with signature, docstring, line range, source), plus a module unit
recording imports, module-level constants and a summary. Behaviour notes list generic
data-handling operations (e.g. ``fillna``, ``dropna``, ``resample``) so later stages can
notice silent data treatment. Other languages are split into line blocks.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from terrakernel.ingest.common import EvidenceBuilder
from terrakernel.ingest.markdown import ingest_markdown_text
from terrakernel.models import Evidence, EvidenceKind, Locator, Source

MAX_SYMBOL_LINES = 160
BLOCK_LINES = 60

# Generic, domain-agnostic operations whose presence changes how data is treated.
NOTABLE_OPS = {
    "fillna", "dropna", "interpolate", "ffill", "bfill", "resample", "shift", "rolling", "tz_localize",
    "tz_convert", "to_datetime", "astype", "clip", "reindex", "merge", "join", "concat", "groupby",
    "replace", "round", "abs", "sqrt", "mean", "sum", "median", "nanmean", "nansum", "where", "isna",
    "notna", "drop_duplicates", "sort_values", "set_index", "loc", "iloc", "read_csv", "to_csv",
}


def ingest_code(source: Source, path: Path, assets_dir: Path) -> list[Evidence]:
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".py":
        return _ingest_python(source.id, text)
    if suffix == ".ipynb":
        return _ingest_notebook(source.id, text)
    return _ingest_blocks(source.id, text)


def _call_names(node: ast.AST) -> list[str]:
    names: list[str] = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Attribute):
                names.append(f.attr)
            elif isinstance(f, ast.Name):
                names.append(f.id)
    return names


def _ingest_python(source_id: str, text: str, line_offset: int = 0, scope: str = "", b: EvidenceBuilder | None = None,
                   module_label: str | None = None) -> list[Evidence]:
    b = b or EvidenceBuilder(source_id)
    lines = text.splitlines()
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        b.add(EvidenceKind.code_block, text[:8000], Locator(line_start=1 + line_offset, line_end=len(lines) + line_offset),
              f"{scope}unparsed" if scope else "unparsed", meta={"syntax_error": str(e)})
        return b.items

    imports: list[str] = []
    constants: dict[str, str] = {}
    symbols: list[dict[str, Any]] = []
    for node in tree.body:
        if isinstance(node, ast.Import | ast.ImportFrom):
            imports.append(ast.unparse(node))
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Name) and node.value is not None:
                    val = ast.unparse(node.value)
                    if len(val) <= 120:
                        constants[t.id] = val
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            symbols.append({"node": node})

    module_doc = ast.get_docstring(tree) or ""
    mod_lines = [f"Module {module_label or source_id}"]
    if module_doc:
        mod_lines.append(f"Docstring: {module_doc}")
    if imports:
        mod_lines.append("Imports: " + "; ".join(imports))
    if constants:
        mod_lines.append("Module-level constants: " + "; ".join(f"{k} = {v}" for k, v in constants.items()))
    mod_lines.append("Top-level symbols: " + ", ".join(s["node"].name for s in symbols))
    module_ev = b.add(
        EvidenceKind.code_module,
        "\n".join(mod_lines),
        Locator(line_start=1 + line_offset, line_end=len(lines) + line_offset, symbol=module_label),
        f"{scope}module" if scope else "module",
        meta={"imports": imports, "constants": constants, "docstring": module_doc},
    )

    for s in symbols:
        node = s["node"]
        start = (node.decorator_list[0].lineno if getattr(node, "decorator_list", None) else node.lineno)
        end = node.end_lineno or node.lineno
        src_lines = lines[start - 1 : end]
        truncated = len(src_lines) > MAX_SYMBOL_LINES
        body = "\n".join(src_lines[:MAX_SYMBOL_LINES]) + ("\n# ... (truncated)" if truncated else "")
        if isinstance(node, ast.ClassDef):
            kind_label = "class"
            signature = f"class {node.name}({', '.join(ast.unparse(x) for x in node.bases)})"
            methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]
        else:
            kind_label = "function"
            signature = f"def {node.name}({ast.unparse(node.args)})" + (
                f" -> {ast.unparse(node.returns)}" if node.returns else ""
            )
            methods = []
        calls = _call_names(node)
        notable = sorted({c for c in calls if c in NOTABLE_OPS})
        used_constants = sorted({n.id for n in ast.walk(node) if isinstance(n, ast.Name) and n.id in constants})
        doc = ast.get_docstring(node) or ""
        header = [f"{kind_label} {node.name} (lines {start + line_offset}-{end + line_offset})", f"Signature: {signature}"]
        if doc:
            header.append(f"Docstring: {doc}")
        if notable:
            header.append("Data-handling operations used: " + ", ".join(notable))
        if used_constants:
            header.append("Uses module constants: " + ", ".join(f"{c} = {constants[c]}" for c in used_constants))
        content = "\n".join(header) + "\n```python\n" + body + "\n```"
        b.add(
            EvidenceKind.code_symbol,
            content,
            Locator(line_start=start + line_offset, line_end=end + line_offset, symbol=node.name),
            f"{scope}{node.name}" if not scope else f"{scope}{node.name}",
            related=[module_ev.id],
            meta={
                "symbol": node.name, "kind": kind_label, "signature": signature, "docstring": doc,
                "calls": sorted(set(calls)), "notable_ops": notable, "uses_constants": used_constants,
                "methods": methods, "truncated": truncated,
            },
        )
    return b.items


def _ingest_notebook(source_id: str, text: str) -> list[Evidence]:
    nb = json.loads(text)
    b = EvidenceBuilder(source_id)
    for idx, cell in enumerate(nb.get("cells", []), start=1):
        src = "".join(cell.get("source", []))
        if not src.strip():
            continue
        if cell.get("cell_type") == "markdown":
            for ev in ingest_markdown_text(source_id, src, scope_prefix=f"cell{idx}"):
                ev.locator.section = f"cell {idx}" + (f" > {ev.locator.section}" if ev.locator.section else "")
                b.items.append(ev)
                b._used.add(ev.id)
        elif cell.get("cell_type") == "code":
            before = len(b.items)
            _ingest_python(source_id, src, scope=f"cell{idx}/", b=b, module_label=f"cell {idx}")
            for ev in b.items[before:]:
                ev.locator.section = f"cell {idx}"
    return b.items


def _ingest_blocks(source_id: str, text: str) -> list[Evidence]:
    b = EvidenceBuilder(source_id)
    lines = text.splitlines()
    for start in range(0, len(lines), BLOCK_LINES):
        chunk = lines[start : start + BLOCK_LINES]
        if any(x.strip() for x in chunk):
            b.add(EvidenceKind.code_block, "\n".join(chunk),
                  Locator(line_start=start + 1, line_end=start + len(chunk)), b.key("", "block"))
    return b.items
