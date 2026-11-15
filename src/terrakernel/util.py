"""Small helpers shared across stages."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def short_hash(text: str, n: int = 12) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:n]


def slugify(text: str, max_len: int = 60) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    text = re.sub(r"-{2,}", "-", text)
    return (text[:max_len].rstrip("-")) or "item"


def source_slug(rel_path: str) -> str:
    stem = rel_path.rsplit(".", 1)[0] if "." in Path(rel_path).name else rel_path
    return re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_").lower() or "source"


def normalize_text(text: str) -> str:
    """Normalization used for quote matching: case, whitespace, dashes and quotes."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("−", "-").replace("–", "-").replace("—", "-")
    text = text.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def normalize_name(text: str) -> str:
    """Normalization used to group knowledge objects that may be the same thing."""
    text = normalize_text(text)
    text = re.sub(r"\(.*?\)", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def relpath(target: Path, start_dir: Path) -> str:
    import os

    return Path(os.path.relpath(target, start_dir)).as_posix()


_VOLATILE_RE = None


def _normalize_volatile(text: str) -> str:
    """Mask generation timestamps (and only those) so regenerated files compare equal.

    Only values of keys that record *when* something was generated are masked
    (``at``, ``generated_at``, ``finished_at``, ``terrakernel-generated``); dates that are part
    of the content, such as a schedule's ``valid_from``, are compared as is.
    """
    import re

    global _VOLATILE_RE
    if _VOLATILE_RE is None:
        _VOLATILE_RE = re.compile(
            r'^(\s*-?\s*"?(?:at|generated_at|finished_at|terrakernel-generated)"?\s*:\s*)["\']?'
            r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?["\']?(,?)\s*$',
            flags=re.M,
        )
    return _VOLATILE_RE.sub(r"\1<ts>\2", text)


def write_text_stable(path: Path, text: str) -> bool:
    """Write ``text`` unless the file already has the same content up to timestamps.

    Returns True when the file was (re)written. Keeping unchanged files untouched makes
    incremental updates report exactly which artifacts changed.
    """
    path = Path(path)
    if path.exists():
        old = path.read_text(encoding="utf-8", errors="replace")
        if old == text or _normalize_volatile(old) == _normalize_volatile(text):
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True
