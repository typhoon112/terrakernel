"""Preserve Word image relationships; embedded OLE objects are never executed."""

from __future__ import annotations

import posixpath
import re
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageOps

from terrakernel.ingest.common import EvidenceBuilder, section_scope
from terrakernel.models import Evidence, EvidenceKind, Locator, Source
from terrakernel.util import short_hash

R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
CAPTION = re.compile(r"^(?:fig(?:ure)?\.?|table|图|表)\s*\d", re.I)


class DocxMedia:
    def __init__(self, archive: ZipFile, source: Source, assets_dir: Path):
        self.source = source
        self.assets_dir = assets_dir
        self.relationships: dict[str, dict[str, str]] = {}
        rel_path = "word/_rels/document.xml.rels"
        if rel_path in archive.namelist():
            for node in ET.fromstring(archive.read(rel_path)):
                self.relationships[node.get("Id", "")] = dict(node.attrib)
        self.media = {
            item.filename: archive.read(item)
            for item in archive.infolist()
            if not item.is_dir() and item.filename.startswith("word/media/")
        }
        self.embeddings = [
            item.filename for item in archive.infolist()
            if not item.is_dir() and item.filename.startswith("word/embeddings/")
        ]
        self.converted: dict[str, tuple[str | None, dict]] = {}
        self.seen: set[str] = set()
        self.figures: list[Evidence] = []
        self.objects: list[Evidence] = []

    def _image(self, member: str) -> tuple[str | None, dict]:
        if member in self.converted:
            return self.converted[member]
        metadata: dict = {"media_part": member}
        data = self.media.get(member)
        if data is None:
            result = None, {**metadata, "parse_status": "missing", "reason": "Image member is missing."}
        else:
            self.assets_dir.mkdir(parents=True, exist_ok=True)
            name = f"docx-{short_hash(self.source.id, 12)}-{short_hash(member, 12)}"
            try:
                with Image.open(BytesIO(data)) as image:
                    image.load()
                    metadata.update(width=image.width, height=image.height)
                    has_alpha = "A" in image.getbands() or "transparency" in image.info
                    image = ImageOps.exif_transpose(image).convert("RGBA" if has_alpha else "RGB")
                    image.thumbnail((1568, 1568))
                    asset = self.assets_dir / f"{name}.png"
                    image.save(asset, format="PNG")
                result = asset.name, {**metadata, "parse_status": "readable"}
            except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as error:
                # Keep a copy for inspection, but unsupported extensions are never sent as model images.
                asset = self.assets_dir / f"{name}{Path(member).suffix.lower()}"
                asset.write_bytes(data)
                result = asset.name, {
                    **metadata, "parse_status": "unreadable",
                    "reason": f"{type(error).__name__}: {error}",
                }
        self.converted[member] = result
        return result

    def add(
        self, builder: EvidenceBuilder, block: ET.Element, locator: Locator,
        section: list[str], block_index: int, related: list[str], caption: str,
    ) -> None:
        parents = {child: parent for parent in block.iter() for child in parent}
        paragraphs = list(block.iter(W + "p"))
        for element in block.iter():
            local = element.tag.rsplit("}", 1)[-1]
            if local not in {"blip", "imagedata", "OLEObject"}:
                continue
            rid = element.get(R + "embed") or element.get(R + "id") or element.get(R + "link")
            if not rid:
                continue
            relationship = self.relationships.get(rid, {})
            target = relationship.get("Target", "")
            external = relationship.get("TargetMode") == "External"
            member = posixpath.normpath(posixpath.join("word", target)) if target else ""
            if target.startswith("/"):
                member = target.lstrip("/")
            current = element
            container = block
            paragraph = None
            while current in parents:
                current = parents[current]
                if current.tag.rsplit("}", 1)[-1] in {"drawing", "pict", "object"}:
                    container = current
                if current.tag == W + "p":
                    paragraph = current
                    break
            position = locator.model_copy()
            if block.tag == W + "tbl" and paragraph is not None:
                position.symbol = f"{position.symbol}, paragraph {paragraphs.index(paragraph) + 1}"
            meta = {
                "format": "docx", "xml_part": "word/document.xml", "body_block": block_index,
                "relationship_id": rid, "relationship_target": target,
            }
            if local == "OLEObject":
                content = "Embedded OLE object is preserved in the original DOCX but was not parsed or executed."
                if element.get("ProgID"):
                    content += f" Object type: {element.get('ProgID')}."
                meta.update(parse_status="unsupported_embedded_object", object_part=member)
                item = builder.add(EvidenceKind.figure, content, position,
                                   builder.key(section_scope(section), "object"), related=related.copy(), meta=meta)
                self.objects.append(item)
                continue
            if not external:
                self.seen.add(member)
            if external:
                asset, image_meta = None, {"parse_status": "external_not_fetched"}
            else:
                asset, image_meta = self._image(member)
            meta.update(image_meta)
            descriptions = list(dict.fromkeys(
                node.get("descr") or node.get("title") for node in container.iter()
                if node.get("descr") or node.get("title")
            ))
            meta.update(alt_text=descriptions, caption=caption)
            content = "Embedded image. Its content must be read visually."
            if descriptions:
                content += "\nSource alternative text: " + " / ".join(descriptions)
            if caption:
                content += "\nAdjacent source caption: " + caption
            if image_meta["parse_status"] != "readable":
                content += "\nImage content could not be decoded; do not infer its contents from this placeholder."
                # A failed PNG decode must not be passed to the vision API merely because of its suffix.
                meta["original_asset"] = asset
                asset = None
            item = builder.add(EvidenceKind.figure, content, position,
                               builder.key(section_scope(section), "figure"), asset=asset,
                               related=related.copy(), meta=meta)
            self.figures.append(item)

    def finish(self) -> None:
        self.source.meta["docx_media"] = {
            "media_files": len(self.media),
            "image_occurrences": len(self.figures),
            "readable_images": sum(meta["parse_status"] == "readable" for _, meta in self.converted.values()),
            "unreadable_images": sum(meta["parse_status"] != "readable" for _, meta in self.converted.values()),
            "unreferenced_media": sorted(set(self.media) - self.seen),
            "embedded_objects": len(self.embeddings),
            "unparsed_embedded_objects": len(self.embeddings),
            "unparsed_object_parts": self.embeddings,
        }
