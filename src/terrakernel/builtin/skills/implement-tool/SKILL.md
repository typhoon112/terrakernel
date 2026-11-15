---
name: implement-tool
description: Use this skill when implementing a documented research method (formula, metric or procedure) as a small, deterministic Python function that TerraKernel will verify against independent reference values from the materials.
license: Apache-2.0
metadata:
  terrakernel-role: builder
  terrakernel-stage: compile
---

# Implement a documented method as a Python function

You get the method objects (definition, formula, variables and units, assumptions,
missing-data rules) and the exact function signature. Write **one** function that
computes the method exactly as documented.

Rules:
- Follow the documented formula literally, including where normalisation happens
  (per element or on the aggregate), units, and percentage scaling.
- Use only the Python standard library, `numpy` and `pandas`. No file, network or
  environment access, no printing, no global state.
- Unless told that the method defines its own missing-value rule, convert inputs with
  `_checks.aligned_arrays(...)` for series and `_checks.as_number(...)` for numbers. These
  raise clear errors for misaligned, empty or missing values; do not fill or drop missing
  values yourself. When the method does define a rule (for example "a missing day breaks a
  run"), implement exactly that rule and never fill values.
- Validate documented preconditions (for example a normaliser must be positive) and raise
  `_checks.ToolInputError` with a message that says how to fix the input.
- Return exactly what the request says: a Python `float` or, when it asks for one, a Python
  `int` (counts and positions, so that callers can index with the result), or a
  `pandas.Series` when the output kind is `series`. Never return a numpy scalar, a
  DataFrame, a dict or a tuple.
- Series inputs may arrive as numpy arrays or lists of consecutive values; handle them the
  same way as a pandas Series without an index.
- Number inputs that are counts (for example a minimum run length) arrive as floats such as
  `3.0`; accept any float that equals an integer.
- Write a docstring that states the formula, the units of inputs and output, and the
  source the definition comes from.
- Do not copy test values into the code. Your function will be checked against reference
  values you have not seen.
- Keep the function generic: never hard-code or mention dataset- or site-specific values
  (dates, capacities, file names, places) in the code or the docstring. Such values reach the
  function as arguments from the repository's configuration.

Return only the code of the function, starting with `def`.
