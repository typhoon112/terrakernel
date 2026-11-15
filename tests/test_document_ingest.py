"""Document formats retain readable evidence and native source locations."""

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from PIL import Image

from terrakernel.ingest import ingest_file, scan_materials
from terrakernel.models import EvidenceKind


def test_docx_preserves_structure_math_and_original_file(tmp_path: Path):
    path = tmp_path / "reference.docx"
    with ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", """<w:document
            xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
          <w:body>
            <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Method</w:t></w:r></w:p>
            <w:p><w:r><w:t>Use </w:t></w:r><m:oMath><m:r><m:t>x=2</m:t></m:r></m:oMath></w:p>
            <w:tbl><w:tr><w:tc><w:p><w:r><w:t>Input</w:t></w:r></w:p></w:tc>
              <w:tc><w:p><w:r><w:t>2</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
          </w:body></w:document>""")
        archive.writestr("word/styles.xml", """<w:styles
            xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:style w:styleId="Heading1"><w:name w:val="heading 1"/></w:style></w:styles>""")
    original = path.read_bytes()
    sources, skipped = scan_materials(tmp_path)
    assert not skipped
    evidence = ingest_file(sources[0], path, tmp_path / "assets")
    assert [item.kind for item in evidence] == [EvidenceKind.heading, EvidenceKind.paragraph, EvidenceKind.table]
    assert evidence[1].content == "Use x=2"
    assert evidence[1].locator.section == "Method"
    assert evidence[1].locator.symbol == "paragraph 2"
    assert evidence[1].locator.page is None
    assert evidence[1].locator.line_start is None
    assert evidence[1].meta["omml"]
    assert evidence[2].meta["rows"] == [["Input", "2"]]
    assert path.read_bytes() == original


def test_html_keeps_source_lines_tables_and_excludes_scripts(tmp_path: Path):
    path = tmp_path / "reference.html"
    path.write_text("""<!doctype html>
<html><head><title>Title</title><style>body { color: red }</style></head>
<body><script>do_not_execute()</script>
<h1>Method &amp; evidence</h1>
<p>Read <a href="https://example.test/reference">the source</a>.</p>
<div hidden>Hidden contents</div>
<table><tr><th>Input</th><th>Value</th></tr>
<tr><td>A</td><td>2</td></tr></table>
</body></html>""", encoding="utf-8")
    sources, skipped = scan_materials(tmp_path)
    assert not skipped
    evidence = ingest_file(sources[0], path, tmp_path / "assets")
    assert [item.kind for item in evidence] == [EvidenceKind.heading, EvidenceKind.paragraph, EvidenceKind.table]
    assert evidence[0].content == "Method & evidence"
    assert evidence[0].locator.line_start == evidence[0].locator.line_end == 4
    assert evidence[1].content == "Read the source."
    assert evidence[1].locator.line_start == 5
    assert evidence[1].meta["links"] == ["https://example.test/reference"]
    assert evidence[2].meta["rows"] == [["Input", "Value"], ["A", "2"]]
    assert evidence[2].locator.line_start == 7
    assert evidence[2].locator.line_end == 8


def test_docx_images_keep_captions_and_report_unreadable_objects(tmp_path: Path):
    path = tmp_path / "illustrated.docx"
    png = BytesIO()
    Image.new("RGB", (20, 10), color="white").save(png, format="PNG")
    with ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", """<w:document
            xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
            xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
            xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:v="urn:schemas-microsoft-com:vml">
          <w:body>
            <w:p><w:r><w:drawing><a:blip r:embed="rImage"/></w:drawing></w:r></w:p>
            <w:p><w:r><w:t>Figure 1. Source caption</w:t></w:r></w:p>
            <w:p><w:r><w:object><v:imagedata r:id="rPreview"/>
              <o:OLEObject r:id="rObject" ProgID="Equation.DSMT4"/></w:object></w:r></w:p>
          </w:body></w:document>""")
        archive.writestr("word/_rels/document.xml.rels", """<Relationships>
          <Relationship Id="rImage" Target="media/image.png"/>
          <Relationship Id="rPreview" Target="media/preview.wmf"/>
          <Relationship Id="rObject" Target="embeddings/equation.bin"/>
        </Relationships>""")
        archive.writestr("word/media/image.png", png.getvalue())
        archive.writestr("word/media/preview.wmf", b"unsupported preview")
        archive.writestr("word/embeddings/equation.bin", b"must not execute")
    sources, _ = scan_materials(tmp_path)
    source = sources[0]
    assets = tmp_path / "assets"
    evidence = ingest_file(source, path, assets)
    figures = [item for item in evidence if item.kind == EvidenceKind.figure]
    assert len(figures) == 3
    assert figures[0].locator.symbol == "paragraph 1"
    assert figures[0].meta["caption"] == "Figure 1. Source caption"
    assert evidence[1].id in figures[0].related
    with Image.open(assets / figures[0].asset) as image:
        assert image.size == (20, 10)
    assert figures[1].asset is None
    assert figures[1].meta["parse_status"] == "unreadable"
    assert figures[2].meta["parse_status"] == "unsupported_embedded_object"
    assert source.meta["docx_media"]["readable_images"] == 1
    assert source.meta["docx_media"]["unreadable_images"] == 1
    assert source.meta["docx_media"]["unparsed_embedded_objects"] == 1
