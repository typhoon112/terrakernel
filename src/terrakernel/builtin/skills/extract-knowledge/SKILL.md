---
name: extract-knowledge
description: Use this skill when turning a batch of evidence units from one research source into typed, evidence-grounded knowledge objects (concepts, claims, methods, datasets, constraints, capabilities) and gaps. Covers papers, documentation, tables, code and figures.
license: Apache-2.0
metadata:
  terrakernel-role: builder
  terrakernel-stage: extract
---

# Extract grounded knowledge from evidence units

You receive evidence units from **one source**. Each unit has an ID such as
`ev:paper_a:p1-b07`, a kind and a locator, followed by its content. Your job is to
record what the source says, faithfully, in a typed structure that downstream code
can check.

## What to extract

| Type | Record it when the source... | Key attributes |
|---|---|---|
| `concept` | names a quantity, entity, term or idea that needs a definition | `definition`, `unit` (if a quantity) |
| `claim` | states a finding, recommendation or comparison | `statement`, `conditions` |
| `method` | defines a formula, metric, algorithm or procedure | `formula` (verbatim notation), `variables` (name, meaning, unit), `inputs`, `outputs`, `assumptions`, `missing_data_handling`, `steps` |
| `dataset` | describes a file or data collection | `file`, `fields` (name, meaning, unit, time_semantics, missing_values), `resolution`, `timezone`, `coverage`, `provenance` |
| `constraint` | gives a rule that must hold or a convention that must be followed | `subject`, `rule`, `valid_from`, `valid_to`, `parameters` (e.g. a value table), `applies_to` |
| `capability` | contains executable code that does something reusable | `symbol`, `signature`, `inputs`, `outputs`, `behavior_notes` (silent assumptions such as hard-coded constants or missing-value filling), `implements` |

Use `attributes` for these keys. Leave a key out, or use `null`, when the source does
not say it. Never fill a value from general domain knowledge.

## Grounding rules (checked by code; violations are rejected)

1. Every object needs at least one entry in `evidence`, with an `evidence_id` from this
   batch and a `quote` copied **verbatim** from that unit's content. Keep the quote
   short (one sentence or one formula line) but exact, including symbols.
2. `basis`:
   - `stated`: the source says it explicitly.
   - `inferred`: you derived it (for example reading a column's meaning from its name
     plus the documentation). Explain how in `basis_note`.
   Never mark guesses as `stated`.
3. Names: use the source's own terms, and put variants in `aliases`. If the source uses a
   subscripted or qualified name (for example `NRMSE_cap`), keep the qualifier. Do not
   merge two different definitions under one generic name.
4. Units, time conventions and missing-data rules are critical. Record them where the source
   states them. When a task-relevant one is not stated, add a **gap**; do not assume.
5. Tables of parameters (for example a value that changes on a date) go into the
   constraint's `parameters` exactly as given.
6. For code, describe what the code actually does, including behaviour that contradicts
   documentation (constants, `fillna`, implicit unit assumptions). These notes matter more
   than the docstring.
7. Figures: record the claim the figure supports only as far as its caption and the
   surrounding text state it.

## Gaps

Add a gap when information a researcher would need to use this source correctly is
missing or ambiguous. Typical cases: a quantity without a unit, a timestamp without an
interval convention or timezone, an unknown issue time or lead time, an undefined
symbol, an unstated handling of missing values. Set `subject` to the name of the object
concerned and `severity` to `blocking` when results would be wrong without it.

## Style

- `summary`: one plain English sentence.
- Prefer several precise objects over one vague object.
- Do not invent relations between sources. Cross-source linking happens later.
