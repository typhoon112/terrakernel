"""Execute the tests emitted for series inputs even when no properties are planned."""

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
