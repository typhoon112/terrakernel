---
name: write-knowledge-docs
description: Use this skill when writing the explanatory body of a knowledge document for an AI-native research repository from grounded knowledge objects, with every statement attributed to its source.
license: Apache-2.0
metadata:
  terrakernel-role: builder
  terrakernel-stage: compile
---

# Write a knowledge document body

You write the Markdown body of one knowledge document. An agent will read it before
doing research, so it must be precise, scannable and fully attributed. TerraKernel adds
the frontmatter, the source list and the evidence appendix itself.

## Content

- Open with a short paragraph saying what the document covers and when to read it.
- Then use headings. Prefer tables for fields, units, parameters and comparisons, and
  fenced blocks for formulas, written exactly as in the sources.
- Say exactly what is documented: units, timestamp conventions, missing-data rules,
  parameters and their validity periods, and assumptions.
- **Conflicts.** When objects define the same thing differently, show the variants side by
  side, say what differs, and say which one applies where the materials decide it (cite
  the deciding convention). Never merge them.
- **Gaps.** Add a section "Open questions" listing the open gaps for these objects. Do not
  answer them.
- **Code.** For code, describe what it actually does, including deviations from the
  documented conventions, and whether it is reused by a repository tool.
- Link to related repository documents with the bundle-relative links you are given, for
  example `[normalised RMSE](/methods/normalised-rmse.md)`. Do not invent paths.

## Attribution (checked by code)

- Every knowledge object you are given has a short `cite` key such as `s3`. End every
  sentence or table row that states a fact with a footnote using that key, for example
  `...in MW.[^s3]`. Use only the keys you are given; cite the object the fact comes from.
- Do not write the footnote definitions and do not quote the source text at length:
  TerraKernel generates the definitions and a separate evidence file with the verbatim
  quotes and locations.
- Mark your own synthesis (comparisons, consequences) with "Note:" and still cite the
  objects it is based on.
- Be economical: an agent reads this document before every task. State each fact once,
  prefer tables to prose for fields and parameters, and do not restate what another
  document already covers; link to it instead.

## Style

Plain English, short sentences, no marketing language, no speculation. Do not include a
top-level `#` title; start with the introductory paragraph and use `##` headings.

Write only the document. Never address the editor or describe your own process ("I left
out...", "if you want..."). If the objects are inconsistent with each other, describe the
inconsistency in the document as an open question, citing the objects involved.
