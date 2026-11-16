# TerraKernel showcase site

The hackathon showcase: workflow, build replay, the three compiled layers and the provenance
chain of every tool, skill and document, rendered from a real build.

## Data

The site is data-driven and contains no dataset of its own. The bundle in `public/data/` is
written by the Python side:

```bash
# from the repository root
uv run terrakernel export-web <built repository> --out web/public/data
```

The bundle's `export-summary.json` records the files, their sizes, the number of page crops and
a leak check (`leaks` must be `[]`). Model calls: none.

## Build

```bash
npm ci
npm run build      # -> dist/
npm run dev        # local preview on 0.0.0.0
```

`vite.config.ts` sets `base: './'`, so `dist/` works under any sub-path (GitHub Pages project
site, plain static server). Routing is hash-based and needs no 404 shim.

## Deploy

`.github/workflows/pages.yml` builds `web/` and publishes `web/dist` to GitHub Pages on every
push to `main`. `public/data/` is committed, so the workflow needs no research materials.
