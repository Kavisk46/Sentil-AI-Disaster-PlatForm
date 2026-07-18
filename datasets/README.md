# Datasets

This directory documents the datasets used by SentinelAI and defines where
sample data should be placed for local development. **Raw datasets are not
stored in this Git repository.**

## Why datasets are not committed to Git

Aerial and satellite imagery datasets used for disaster damage assessment are
typically tens to hundreds of gigabytes in size, may carry redistribution
restrictions from their source provider, and change independently of the
application code. Committing them would bloat repository history
irreversibly and make cloning impractical for contributors. Instead:

- **Raw and full-size datasets** are stored in external, versioned object
  storage (e.g., an S3-compatible bucket or a dedicated data-versioning tool
  such as DVC), referenced by pointer files or configuration rather than
  committed directly.
- **Small, representative sample data** needed to run the application locally
  or in tests lives under [`datasets/samples/`](samples/) and *is* committed,
  provided it is small (a few megabytes at most) and appropriately licensed
  for redistribution.

## Where to place sample datasets

Place small, redistributable sample imagery and accompanying metadata under
`datasets/samples/`, using a subdirectory per source or scenario, for example:

```
datasets/samples/
├── post-hurricane-imagery/
├── post-earthquake-imagery/
└── road-network-fixtures/
```

Each sample subdirectory should include a short `README.md` describing:

- The source of the sample (e.g., public dataset name, agency, or synthetic origin).
- Its license and any attribution requirements.
- What it is used for (e.g., "used by AI engine unit tests" or "used for frontend map fixtures").

## Working with full datasets locally

Instructions for connecting to and syncing full-size datasets from external
storage will be documented here once the data ingestion pipeline is
implemented (see Phase 2 and Phase 4 in
[`PROJECT_ROADMAP.md`](../PROJECT_ROADMAP.md)).
