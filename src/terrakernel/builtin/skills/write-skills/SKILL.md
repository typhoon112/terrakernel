---
name: write-skills
description: Use this skill when writing the instructions of a domain Agent Skill (SKILL.md body) that tells a research agent how to complete one research task with the repository's knowledge documents and verified tools.
license: Apache-2.0
metadata:
  terrakernel-role: builder
  terrakernel-stage: compile
---

# Write a research workflow skill

You write the Markdown body of one `SKILL.md`. A research agent working in the
repository will follow it step by step. TerraKernel adds the frontmatter.

## Required sections

1. `## When to use`: the task and the questions it answers.
2. `## Read first`: the knowledge documents to read, as repository-relative links (for
   example `[conventions](../../../knowledge/conventions/x.md)`). Use the paths you are given.
3. `## Procedure`: numbered steps. Each step either reads something, calls a tool, or
   checks a condition. Show tool calls as short Python snippets that run from the
   repository root, using only the functions you are given:
   ```python
   import sys; sys.path.insert(0, "tools")
   import research_tools as rt
   ```
   Say what each step must confirm, for example that units are already canonical, how
   many rows are left, or which parameter value applies at a boundary.
4. `## Stop and report`: the conditions under which the agent must stop, or report an
   open question, instead of guessing (use the open gaps you are given).
5. `## Output`: what the final answer must contain, including numbers with units, the
   definitions used (cite the knowledge documents), the sample size, transformations
   applied, and open questions.
6. `## Gotchas`: the pitfalls that the materials expose, such as conflicting definitions,
   legacy code that must not be used, or conventions that differ between files.

## Rules

- Use only tools that exist (the list you are given, with exact signatures) and
  documents that exist.
- Do not restate formulas; point to the knowledge document and the tool.
- The data runtime already converts units and timestamp conventions; tell the agent to
  rely on it and to check `attrs["terrakernel"]`, not to redo conversions by hand.
- Keep it under 150 lines.
