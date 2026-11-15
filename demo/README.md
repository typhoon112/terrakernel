# TerraKernel demo

Two built showcases, each a research repository plus its generated site. Both use synthetic
materials from `examples/`; the build and the agent runs call the model endpoint configured
through `ANTHROPIC_*`, so they cost a few dollars.

Replace `YYYYMMDD` with the run date; run these commands from the repository root.

```
uv run terrakernel demo --out artifacts/YYYYMMDD/demo            # build both (about 10 minutes)
uv run terrakernel serve artifacts/YYYYMMDD/demo/site --port 8765
```

What the command does for each showcase:

1. `terrakernel init` with the example's materials and tasks;
2. `terrakernel build` (ingest → extract → reconcile → plan → compile → validate);
3. `terrakernel answer` twice (wind): people answer two open questions, which become
   human-confirmed knowledge and propagate through an incremental update;
4. an incremental update after a materials change (wind): the capacity expansion date moves
   from 2023-07-01 to 2023-06-01, and the independent reference solution is run again so that
   the agent runs are graded against the answer for the changed materials;
5. `terrakernel eval` with the graded agent runs shown on the site;
6. `terrakernel gallery` exports both sites under one entry page into `<out>/site`.

`site.yaml` and `site-heatwave.yaml` give each site its title and headline in English and
Chinese (`title`, `title_zh`, `hero_title`, `hero_title_zh`).

Everything the site shows (cases, evidence crops, code lines, dependency graph, run replays)
is read from the built repository; nothing is hand-written.
