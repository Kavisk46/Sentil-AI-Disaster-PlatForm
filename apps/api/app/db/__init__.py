"""Milestone F5 — PostgreSQL persistence.

`app/db/` owns everything SQLAlchemy-specific: the engine/session factory
(`session.py`), the declarative ORM models (`models.py`), and nothing
else. ORM models are never imported outside `app/services/postgres_*.py`
repository implementations — the rest of the application (services,
routes, `app.ml`, `app.intelligence`) only ever sees the existing
Pydantic/dataclass domain schemas (`AnalysisRecord`, `BuildingDamage`,
...), exactly as it did before this milestone. See
`docs/architecture/production.md`, "Persistence," for the full design
and why search zones/recommendations/routes are deliberately NOT
persisted here.
"""
