"""Built-in builder skills: Markdown instructions (Agent Skills format) used as model prompts."""

from __future__ import annotations

from functools import cache
from pathlib import Path

import yaml

SKILLS_DIR = Path(__file__).parent / "skills"


@cache
def load_skill(name: str) -> tuple[dict, str]:
    """Return (frontmatter, body) of a builder skill."""
    text = (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text
    _, fm, body = text.split("---", 2)
    return yaml.safe_load(fm) or {}, body.strip()


def skill_body(name: str) -> str:
    return load_skill(name)[1]


def skill_version(name: str) -> str:
    import hashlib

    return hashlib.sha256((SKILLS_DIR / name / "SKILL.md").read_bytes()).hexdigest()[:12]
