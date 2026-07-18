# Sample Datasets

This directory holds small, redistributable sample data used for local
development, demos, and automated tests. It intentionally does not contain
full-size or production imagery — see [`datasets/README.md`](../README.md)
for why raw datasets are kept out of Git and where they are stored instead.

## Adding a new sample

When adding a sample dataset to this directory:

1. Create a subdirectory named for the scenario or source (e.g.,
   `post-hurricane-imagery/`).
2. Keep the total size small — sample data exists to make the platform
   runnable and testable, not to be a working dataset.
3. Include a `README.md` in the subdirectory documenting the sample's source,
   license, and intended use.

No sample data has been added yet; this directory will be populated as the
imagery ingestion pipeline (Phase 2) and AI engine (Phase 4) are implemented.
