# Results

This directory holds **generated output only** — raw per-experiment JSON
(`raw/`), any processed/aggregated tables (`processed/`), and generated
SVG figures (`figures/`). Nothing under `research/results/` is a
committed dataset or model weight, and nothing here is hand-written:
everything is produced by `research/core/result_store.py`,
`research/core/report.py`, or `research/core/experiment_figures.py` from
real measured `ExperimentResult` records.

Contents of `raw/`, `processed/`, and `figures/` are gitignored (see the
repo root `.gitignore`) — only this README and the empty directory
placeholders are tracked, so the layout exists in a fresh checkout
without ever committing a real run's output.

Per Milestone 10: **no large experiments run automatically.** This
directory stays empty until someone deliberately runs the framework
against a real scenario set.
