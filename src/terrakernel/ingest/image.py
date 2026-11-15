"""Image ingest: keep the image as an asset; its meaning is extracted later with vision."""

from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

from terrakernel.ingest.common import EvidenceBuilder
from terrakernel.models import Evidence, EvidenceKind, Locator, Source


def ingest_image(source: Source, path: Path, assets_dir: Path) -> list[Evidence]:
    b = EvidenceBuilder(source.id)
    assets_dir.mkdir(parents=True, exist_ok=True)
    target = assets_dir / f"{source.id}{path.suffix.lower()}"
    shutil.copyfile(path, target)
    with Image.open(path) as im:
        w, h = im.size
    b.add(
        EvidenceKind.image,
        f"Image file {source.path} ({w}x{h} px). Its content must be read visually.",
        Locator(),
        "image",
        asset=target.name,
        meta={"width": w, "height": h},
    )
    return b.items
