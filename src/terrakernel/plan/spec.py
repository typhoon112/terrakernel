"""Repository Spec: the machine-readable build plan, and the planner's raw output schema."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ----------------------------------------------------------------------------- planner output (model-facing)


class DocPlan(BaseModel):
    path: str = Field(description="Path relative to knowledge/, e.g. datasets/site-data.md")
    okf_type: str
    title: str
    description: str = Field(description="One sentence")
    object_ids: list[str]
    task_ids: list[str] = Field(default_factory=list)


class UnitChoice(BaseModel):
    quantity: str
    unit: str


class ConventionsPlan(BaseModel):
    canonical_units: list[UnitChoice]
    canonical_time_convention: Literal["interval_ending", "interval_beginning", "instant"]
    evidence_object_ids: list[str]


class ColumnPlan(BaseModel):
    column: str
    quantity: str
    unit: str | None = Field(description="Documented unit, or null if not documented")
    evidence_object_ids: list[str]


class DatasetPlan(BaseModel):
    name: str = Field(description="Short snake_case key used by load_dataset()")
    file: str = Field(description="File path as in the materials")
    format: Literal["table", "netcdf"] = Field(default="table", description="table: CSV/TSV/Excel/Parquet; netcdf: gridded")
    sheet: str | None = Field(default=None, description="Excel sheet name, if the file has several sheets")
    profile_object_id: str
    description: str
    time_column: str | None
    time_convention: Literal["interval_ending", "interval_beginning", "instant", "unknown"]
    timezone: str | None
    resolution: str | None = Field(description="pandas offset alias such as 1h or 15min")
    value_columns: list[ColumnPlan]
    missing_values: Literal["exclude", "keep", "unknown"]
    evidence_object_ids: list[str]
    open_issues: list[str] = Field(default_factory=list)


class ScheduleEntry(BaseModel):
    valid_from: str = Field(description="ISO 8601 instant with timezone")
    value: float


class ParameterPlan(BaseModel):
    name: str = Field(description="snake_case parameter name")
    description: str
    quantity: str
    unit: str
    lookup: Literal["interval_start", "interval_end", "instant", "unknown"]
    schedule: list[ScheduleEntry]
    evidence_object_ids: list[str]


class ToolInput(BaseModel):
    name: str
    kind: Literal["series", "number", "string"]
    description: str
    unit: str | None = None


class ToolPlan(BaseModel):
    name: str
    purpose: str
    strategy: Literal["wrap_existing", "candidate", "knowledge_only"]
    output_kind: Literal["number", "series"] = Field(
        default="number", description="number: one float (testable against stated results); series: a per-row result")
    method_ids: list[str]
    capability_id: str | None = None
    inputs: list[ToolInput]
    output_description: str
    output_unit: str | None = None
    test_object_ids: list[str] = Field(default_factory=list)
    properties: list[Literal["zero_when_equal", "non_negative", "symmetric", "scale_invariant"]] = Field(
        default_factory=list
    )
    missing_values: Literal["reject", "defined_by_method"] = Field(
        default="reject",
        description="reject: NaN inputs raise (the caller selects a common valid sample first); defined_by_method: "
                    "the documented method itself says how missing values count (e.g. a missing day breaks a run)")
    notes: str = ""


class SkillPlan(BaseModel):
    name: str
    task_id: str
    description: str
    tools: list[str]
    docs: list[str]
    steps: list[str]


class GapPlan(BaseModel):
    description: str
    severity: Literal["blocking", "warning"]
    related_ids: list[str] = Field(default_factory=list)


class RepositoryPlan(BaseModel):
    summary: str = Field(description="Two or three sentences describing what the repository enables")
    docs: list[DocPlan]
    conventions: ConventionsPlan
    datasets: list[DatasetPlan]
    parameters: list[ParameterPlan]
    tools: list[ToolPlan]
    skills: list[SkillPlan]
    capability_gaps: list[GapPlan]


# ----------------------------------------------------------------------------- compiled spec (stored as spec.yaml)

ArtifactKind = Literal["knowledge_doc", "computation_doc", "config", "runtime", "tool", "test", "skill", "entry",
                       "adapter", "source"]
ArtifactStatus = Literal["planned", "blocked", "generated", "verified", "candidate", "failed", "skipped"]


class Artifact(BaseModel):
    id: str
    kind: ArtifactKind
    path: str
    title: str = ""
    description: str = ""
    objects: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    strategy: str | None = None
    acceptance: list[str] = Field(default_factory=list)
    status: ArtifactStatus = "planned"
    blocked_by: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)
    fingerprint: str | None = None


class RepositorySpec(BaseModel):
    version: str = "1"
    generated_at: str
    generated_by: str
    summary: str
    plan: RepositoryPlan
    artifacts: list[Artifact]
    issues: list[str] = Field(default_factory=list)

    def artifact(self, artifact_id: str) -> Artifact | None:
        return next((a for a in self.artifacts if a.id == artifact_id), None)

    def by_kind(self, kind: str) -> list[Artifact]:
        return [a for a in self.artifacts if a.kind == kind]
