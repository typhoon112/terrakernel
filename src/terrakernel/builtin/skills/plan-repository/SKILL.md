---
name: plan-repository
description: Use this skill when planning the AI-native research repository for a source knowledge base - choosing which knowledge documents to write, turning documented data semantics and parameters into executable configuration, deciding which tools to build (reuse existing code, or implement documented formulas for independent verification) and which skills to write for each research task.
license: Apache-2.0
metadata:
  terrakernel-role: builder
  terrakernel-stage: plan
---

# Plan an AI-native research repository

You receive a source knowledge base (objects, relations, gaps) and the research tasks
the repository must support. You produce a **plan**; code will check it and compile the
repository from it. Every decision must be traceable to knowledge objects; put the IDs
in the `*_object_ids` fields.

## 1. Knowledge documents (`docs`)

Group objects into documents an agent can read on demand. Aim for 4 to 10 documents.

- Group by meaning and use: one document per data collection (its files, fields, units,
  time conventions and rules), per method family (definitions, formulas, variants,
  conflicts), per convention or policy, and per significant code module. Do not create
  one document per object.
- A conflict between definitions belongs in the document of the concept they define,
  with the convention that decides between them, if the materials give one.
- Paths are relative to `knowledge/`, in lowercase kebab-case, grouped in folders such as
  `datasets/`, `methods/`, `conventions/` and `code/`.
- `okf_type` is a short descriptive type such as `Dataset`, `Metric`, `Method`,
  `Convention`, `Code Module` or `Reference`.
- Include every object a task needs in at least one document.

## 2. Executable data semantics (`conventions`, `datasets`, `parameters`)

This is where documented knowledge becomes configuration that code enforces.

- `datasets`: one entry per **data file or sheet** (use the profiled dataset object IDs; an
  Excel file has one profile per sheet, so give `sheet`). Set `format: netcdf` for NetCDF
  files: their value columns are the data variables, and units stated in the file's own
  attributes count as documented. Give the
  time column, the timestamp convention (`interval_ending`, `interval_beginning` or
  `instant`), the timezone, the resolution as a pandas offset (`1h`, `15min`, `1D`), every
  value column with its physical quantity and unit, and how missing values are treated
  (`exclude` when they must not be imputed). Use `unknown` or null when the materials do
  not say, and list the problem in `open_issues`. **Never guess a unit or a convention.**
- `conventions`: the canonical unit for each quantity, and the canonical timestamp
  convention the repository's tools will use, both as documented (for example "errors
  are reported in MW", or the convention the reference measurements use).
- `parameters`: values that change over time on documented dates (for example a capacity
  schedule). Give the schedule exactly as documented, and say at which point of an
  interval the value is looked up (`interval_start`, `interval_end` or `instant`) if the
  materials say so.
- Units must be written as plain symbols such as `W`, `kW`, `MW`, `kWh`, `m/s`, `degC`, `%`.

## 3. Tools (`tools`)

Plan the computational functions the tasks need beyond the generic runtime. The runtime
always provides `load_dataset`, `load_series`, `common_valid_sample`, `parameter_series`
and `convert_units`, driven by the configuration above: loaded data is already in the
canonical units and timestamp convention, `common_valid_sample` keeps only rows where every
series is present, and `parameter_series` applies the documented lookup rule. Do not plan
those again.

For each additional tool choose a strategy:

- `wrap_existing`: the materials contain code that computes it correctly enough to reuse.
  Give the `capability_id` and its symbol. Wrapping adds input checks; it does not change
  the computation. If the code deviates from the documented method (hard-coded constants,
  missing-value filling), either plan a separate `candidate` for the documented method or
  restrict the wrapped tool to the part that is correct.
- `candidate`: only a formula or description exists. TerraKernel will implement it from
  the method objects and then verify it against independent references. List those
  references in `test_object_ids`: worked examples, tables or stated results in the
  materials that give inputs and expected outputs.
- `knowledge_only`: the method should be documented but no tool is justified.

Tool names are snake_case Python identifiers. Inputs are pandas Series or floats. Each
input names its unit. Data access (choosing a file, variable, grid cell or column) is the
runtime's job, not a tool's: tools receive values. If a task needs a spatial selection, plan a
small candidate tool that takes the coordinate arrays as series and returns an index, or let
the skill do it with the runtime and plain pandas/xarray. Prefer tools that return **one
number** (`output_kind: number`), for example a count, a mean or an error metric, because
those can be checked against results stated in the materials. Use `output_kind: series` only
when the per-row result itself is needed; such tools can only be property-tested. Integer-like
inputs (a minimum run length, a window size) are `number` inputs. Set `missing_values:
defined_by_method` only when the documented method says how missing values count (for
example "a missing day breaks a run"); otherwise tools reject missing values and the caller
selects a common valid sample. Prefer one tool per documented variant (for example one per
normalisation) over a single tool with a mode switch.

A tool's `purpose`, `notes` and input descriptions must be generic: they describe the
computation, not the case. Do not repeat case-specific values (dates, capacities, site or
file names); those belong in `parameters` and `datasets`, which can change without
rebuilding the tool.

`properties` are generic invariants the tool must satisfy; `zero_when_equal` and
`symmetric` refer to the first two series inputs, and `scale_invariant` means multiplying
every input by the same factor leaves the result unchanged. Only list properties that the
documented definition guarantees.

## 4. Skills (`skills`)

Plan one skill per research task. A skill is a workflow: which documents to read, which
tools to call in which order, which conditions to check, when to stop and report a gap,
and what to output. Use kebab-case names that describe the task, without the words
"claude" or "anthropic". The `description` (at most 1024 characters) must start with
"Use this skill when" and say both what the skill does and when to use it.

## 5. Capability gaps

List what the repository cannot support because the materials are silent or
contradictory and the task needs it. Never paper over a gap with an assumption.
