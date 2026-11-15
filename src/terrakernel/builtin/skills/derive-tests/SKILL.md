---
name: derive-tests
description: Use this skill when deriving independent test cases for a research tool from worked examples, tables and stated results in the source materials, with every input and expected value traceable to quoted evidence.
license: Apache-2.0
metadata:
  terrakernel-role: builder
  terrakernel-stage: compile
---

# Derive reference tests from the materials

You get a tool signature and evidence units that contain worked examples, tables or
stated results. Produce test cases whose inputs **and** expected outputs come from the
materials, never from your own calculation.

For each test case:
- `inputs`: values for every tool input. Series inputs are lists of numbers in the order
  given by the source (for example the rows of a worked-example table). Number inputs are
  single numbers. Convert units only if the tool's input unit differs from the source's unit,
  and say so in `notes`.
- `expected`: the result **stated** in the materials, in the tool's output unit.
- `expected_quote`: the exact text from the evidence that states the expected value
  (it must contain the number as written).
- `input_evidence_ids` and `expected_evidence_id`: where the values come from.
- `notes`: anything needed to understand the case.

Only include a case when the source states the result explicitly. If the source's stated
result contradicts its own table, skip that case and explain it in `skipped`. Do not
invent cases, and do not compute expected values yourself.
