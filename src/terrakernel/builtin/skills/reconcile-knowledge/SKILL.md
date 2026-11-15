---
name: reconcile-knowledge
description: Use this skill when relating knowledge objects extracted separately from several research sources - deciding which objects are the same, which are variants or conflicting definitions of one idea, how code relates to methods and documentation to data files, and which reported gaps are answered by another source.
license: Apache-2.0
metadata:
  terrakernel-role: builder
  terrakernel-stage: reconcile
---

# Reconcile knowledge across sources

Each source was extracted on its own, so the catalog contains one object per source even
when several sources talk about the same thing. Your job is to connect them **without
destroying information**.

## Relations you may propose

| type | use when |
|---|---|
| `same_as` | two objects denote exactly the same thing with compatible content (for example a data file described in documentation and the profiled file itself, or the same quantity defined identically) |
| `possibly_same_as` | probably the same, but you cannot confirm it from the catalog |
| `variant_of` | `src` is one specific definition or variant of the broader idea `dst` (use with an umbrella concept, see below) |
| `conflicts_with` | two definitions, rules or claims cannot both be applied as written (different formulas, units, conventions or numbers for the same named thing). Explain the difference precisely in `note` |
| `implements` | a capability (code) computes a method. Say in `note` whether the code matches the method's definition and where it deviates (for example a hard-coded constant instead of a time-varying input, or filling missing values) |
| `describes` | documentation describes a data file, a dataset or a capability |
| `applies_to` | a constraint or convention applies to a dataset, method or capability |
| `uses` | a method or capability uses a dataset, concept or parameter |
| `depends_on` | an object needs another object to be usable (for example a method needs a parameter table) |

Rules:
- `src` and `dst` must be IDs from the catalog, or the `name` of an umbrella concept you propose in the same answer.
- Never merge conflicting definitions. Two different formulas sharing one name are two
  methods: relate each to an umbrella concept with `variant_of` and to each other with
  `conflicts_with`.
- Prefer few, meaningful relations over many trivial ones. Do not relate objects only
  because they come from the same source.
- When documentation states which variant is the convention to use, add an `applies_to`
  relation from that convention (constraint) to the chosen variant, and say so in the note.

## Umbrella concepts

When two or more sources define different variants of one idea (for example two
normalisations of the same error metric), propose an umbrella concept with a neutral
name, a one-sentence summary and its `member_ids`. Do not create umbrella concepts for
things that have only one definition.

## Gaps

For every open gap, decide whether another source answers it. Resolve a gap only if a
catalog object states the missing information explicitly; cite those objects in
`resolved_by` and explain briefly. Leave everything else open. Never resolve a gap with
general domain knowledge.

You may add `new_gaps` for problems that only appear across sources, for example two
conflicting definitions where the materials never say which one a task should use, or
code that contradicts the documented convention.
