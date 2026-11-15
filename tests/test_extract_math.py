"""Original Word equation structure augments prompts without changing quoted evidence."""

import re
import xml.etree.ElementTree as ET

from terrakernel.extract import _format_evidence, batches
from terrakernel.models import Evidence, EvidenceKind

FORMULA = """<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"
    xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <m:f><m:fPr><m:ctrlPr><w:rPr><w:rFonts w:ascii="Cambria Math"/></w:rPr></m:ctrlPr></m:fPr>
    <m:num><m:sSub><m:e><m:r><m:rPr><m:sty m:val="i"/></m:rPr><m:t>x</m:t></m:r></m:e>
      <m:sub><m:r><m:t>1</m:t></m:r></m:sub></m:sSub></m:num>
    <m:den><m:sSup><m:e><m:r><m:t>y</m:t></m:r></m:e>
      <m:sup><m:r><m:t>2</m:t></m:r></m:sup></m:sSup></m:den>
  </m:f>
  <m:nary><m:naryPr><m:chr m:val="∑"/><m:limLoc m:val="undOvr"/></m:naryPr>
    <m:sub><m:r><m:t>i=0</m:t></m:r></m:sub><m:sup><m:r><m:t>N</m:t></m:r></m:sup>
    <m:e><m:r><m:t>i</m:t></m:r></m:e></m:nary>
</m:oMath>"""


def evidence(name: str, content: str, **meta) -> Evidence:
    return Evidence(id=f"ev:source:{name}", source_id="source", kind=EvidenceKind.paragraph,
                    content=content, content_hash="unchanged", meta=meta)


def test_prompt_preserves_fraction_scripts_and_nary_without_changing_quote_text():
    ev = evidence("equation", "x1y2i=0Ni", omml=[FORMULA])
    original = ev.model_dump_json()
    prompt = _format_evidence(ev)
    assert '<evidence id="ev:source:equation" kind="paragraph">\nx1y2i=0Ni\n</evidence>' in prompt
    root = ET.fromstring(re.search(r"(<oMath>.*?</oMath>)", prompt, re.S)[1])
    assert root.findtext("f/num/sSub/e/r/t") == "x"
    assert root.findtext("f/num/sSub/sub/r/t") == "1"
    assert root.findtext("f/den/sSup/e/r/t") == "y"
    assert root.findtext("f/den/sSup/sup/r/t") == "2"
    assert root.find("nary/naryPr/chr").get("val") == "∑"
    assert root.findtext("nary/sub/r/t") == "i=0"
    assert root.findtext("nary/sup/r/t") == "N"
    assert all(noise not in prompt for noise in ["Cambria", "rFonts", "rPr", "ctrlPr", "xmlns"])
    assert "quotes must still be copied verbatim" in prompt
    assert "unsupported OLE" in prompt
    assert ev.model_dump_json() == original


def test_math_context_counts_towards_budget_and_other_prompts_stay_identical():
    plain = [evidence(str(index), "x" * 100) for index in range(3)]
    assert batches(plain, budget=600) == [plain[:2], plain[2:]]
    assert _format_evidence(plain[0]) == (
        '<evidence id="ev:source:0" kind="paragraph">\n' + "x" * 100 + "\n</evidence>"
    )
    formula = evidence("equation", "x1y2i=0Ni", omml=[FORMULA])
    # The flattened text alone would fit with both paragraphs; its full structure does not.
    assert batches([plain[0], formula, plain[1]], budget=600) == [[plain[0]], [formula], [plain[1]]]
