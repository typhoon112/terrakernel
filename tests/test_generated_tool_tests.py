"""Execute the tests emitted for series inputs even when no properties are planned."""

import pytest

from terrakernel.compile.tools import render_candidate_module, render_test_file, run_pytest, write_runtime
from terrakernel.plan.spec import ToolInput, ToolPlan
from terrakernel.project import Project, ProjectConfig


def test_generated_series_missing_value_checks_run_without_properties(tmp_path):
    project = Project.create(tmp_path, ProjectConfig(name="test", goal="test", materials="sources"))
    try:
        write_runtime(tmp_path)
        package = tmp_path / "tools/research_tools"
        (package / "__init__.py").write_text("")
        (tmp_path / "tests").mkdir()
        for output_kind in ("number", "series"):
            tool = ToolPlan(name=f"sample_{output_kind}", purpose="Read supplied values", strategy="candidate",
                            method_ids=[], inputs=[ToolInput(name="values", kind="series", description="Input")],
                            output_description="Result", output_kind=output_kind, properties=[], missing_values="reject")
            result = "float(values.sum())" if output_kind == "number" else "pd.Series(values)"
            code = (
                f"def {tool.name}(values):\n"
                "    values = np.asarray(values, dtype=float)\n"
                "    if np.isnan(values).any():\n"
                "        raise ValueError('Missing values')\n"
                f"    return {result}\n"
            )
            module = render_candidate_module(tool, code, project)
            assert "Verified against" not in module
            assert "Validation status and source references: see registry.json" in module
            (package / "tools" / f"{tool.name}.py").write_text(module)
            cases = [{"id": "source-example", "inputs": {"values": [2, 3]}, "expected": 5,
                      "abs_tol": 1e-9, "source": "ev:source:example", "quote": "2 + 3 = 5"}]
            tests = render_test_file(tool, cases, [])
            assert tests.count("def _random_inputs(") == 1
            (tmp_path / "tests" / f"test_{tool.name}.py").write_text(tests)
        result = run_pytest(tmp_path, "tests")
        assert result["returncode"] == 0, result["output"]
        assert result["passed"] == 4
        assert result["failed"] == result["errors"] == 0
    finally:
        project.close()


def test_numbers_in_the_materials_are_read_as_written():
    """Reference cases are checked against the cited text, so its numbers must be read correctly."""
    from terrakernel.compile.tools import _numbers, _quoted_precision

    # thousands separators in English-language tables
    assert {50000.0, 10000.0} <= set(_numbers("Facility A 50,000 metric tons; Facility B 10,000 metric tons"))
    assert 1234.5 in _numbers("1,234.5 MWh") and 1.234 not in _numbers("1,234.5 MWh")
    assert 1234567.0 in _numbers("1,234,567 t")
    # a decimal comma stays a decimal comma
    assert _numbers("6,7 亿kWh") == [6.7] and _numbers("0,25") == [0.25]
    # numbers that touch a unit or a CJK character
    assert _numbers("铁矿石的基准值为100kgCO2/单位") == [100.0]
    assert _numbers("排放90+110+100=300kgCO2") == [90.0, 110.0, 100.0, 300.0]
    assert _numbers("(780+2.9×1800)/3=2000 kgCO2") == [780.0, 2.9, 1800.0, 3.0, 2000.0]
    assert -42.0 in _numbers("责任 −42 万tCO2") and -630.0 in _numbers("-630 gCO2/kWh")
    # identifiers and section numbers are not quantities
    assert _numbers("see ev t11, p4-b03 and section 1.2.3") == []
    assert _numbers("CO2 and N2O per m3") == []
    # precision follows the digits shown
    assert _quoted_precision(100.0, "基准值为100kgCO2/单位") == pytest.approx(0.5, abs=1e-6)
    assert _quoted_precision(50000.0, "total 50,000 t") == pytest.approx(0.5, abs=1e-6)
    assert _quoted_precision(0.6, "grid average 0.6 mt/MWh") == pytest.approx(0.05, abs=1e-6)
    assert _quoted_precision(7.0, "the value is 6") is None
