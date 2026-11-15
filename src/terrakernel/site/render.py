"""Markdown rendering for the site: footnotes become links to the cited knowledge object."""

from __future__ import annotations

import re
from typing import Any

import yaml
from markdown_it import MarkdownIt
from mdit_py_plugins.deflist import deflist_plugin
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.util import ClassNotFound

from terrakernel.util import slugify

PYGMENTS_CSS = HtmlFormatter(style="tango").get_style_defs(".codehilite")
CODE_FENCE_RE = re.compile(r"```(\w*)\n(.*?)```", re.S)


def _highlight_code(code: str, lang: str) -> str:
    try:
        lexer = get_lexer_by_name(lang) if lang else guess_lexer(code)
    except ClassNotFound:
        lexer = get_lexer_by_name("text")
    return highlight(code, lexer, HtmlFormatter(cssclass="codehilite", nowrap=False))


def _render_code_fences(text: str) -> tuple[str, dict[str, str]]:
    """Replace fenced code with highlighted HTML before markdown parsing (keeps indentation intact)."""
    store: dict[str, str] = {}

    def repl(m: re.Match[str]) -> str:
        key = f"CODEBLOCK{len(store)}X"
        store[key] = _highlight_code(m.group(2), m.group(1))
        return key

    return CODE_FENCE_RE.sub(repl, text), store


CITE_RE = re.compile(r"\[\^([^\]\s]+)\](?!:)")
FOOTNOTE_DEF_RE = re.compile(r"^\[\^[^\]]+\]:.*(?:\n(?!\[\^|\n).*)*", re.M)


def md_to_html(text: str, object_href=None, base_href: str = "", wiki_links: dict[str, str] | None = None,
               link_href=None) -> str:
    """Render Markdown to HTML.

    Footnote citations ``[^object-id]`` become numbered links: ``object_href(object_id)`` decides
    the target (``None`` renders the citation as unresolved). Footnote definitions are dropped,
    because every citation links to the page of the cited knowledge object instead.
    ``base_href`` prefixes links from the Markdown. Callback and wiki links are
    already relative to the rendered page and are kept unchanged.
    """
    text, code_store = _render_code_fences(text)
    text = FOOTNOTE_DEF_RE.sub("", text)
    order: dict[str, int] = {}
    marks: dict[str, str] = {}

    def cite(m: re.Match[str]) -> str:
        label = m.group(1)
        n = order.setdefault(label, len(order) + 1)
        key = f"CITEMARK{len(marks)}X"
        href = object_href(label) if object_href else None
        cls = "cite" if href else "cite cite-missing"
        target = f' href="{href}"' if href else ""
        marks[key] = f'<sup class="{cls}"><a{target} title="{label}">{n}</a></sup>'
        return key

    text = CITE_RE.sub(cite, text)
    md = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table").enable("strikethrough")
    md.use(deflist_plugin)
    html = md.render(text)
    if link_href:
        html = re.sub(r'href="([^"]+)"', lambda m: f'href="{link_href(m.group(1))}"', html)
    elif base_href:
        html = re.sub(r'(href|src)="(?!https?://|#|mailto:|/)([^"]+)"',
                      lambda m: f'{m.group(1)}="{base_href}{m.group(2)}"', html)
    for key, block in code_store.items():
        html = html.replace(f"<p>{key}</p>", block).replace(key, block)
    for key, mark in marks.items():
        html = html.replace(key, mark)
    # tables scroll horizontally instead of breaking the layout
    html = html.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")
    if wiki_links:
        for oid, href in wiki_links.items():
            label = oid.split(":", 1)[-1]
            html = html.replace(f"[[{oid}]]", f'<a class="obj" href="{href}">{label}</a>')
    return html


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    try:
        fm = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError:
        return {}, text
    return (fm if isinstance(fm, dict) else {}), text[end + 4:].strip()


def object_page_name(oid: str) -> str:
    return slugify(oid, 80)
