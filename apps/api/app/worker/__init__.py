"""Milestone F5 — the background worker process.

`app/worker/main.py` is the process entrypoint
(`python -m app.worker.main`): it eagerly loads the real damage-detection
model once at startup (fixing F4's in-API-request cold start),
publishes its lifecycle state to Redis, then runs an RQ worker loop.
`app/worker/tasks.py::process_analysis_job` is the job function RQ
actually invokes per queued analysis — see `app/services/job_queue.py`
for why it's referenced by import string rather than a direct import
from the API process.

This package is the *only* place (besides `app/api/deps.py`'s own
`get_building_localizer`/`get_damage_classifier`, which it calls
directly, not through FastAPI) that constructs a real, loaded
`DamageModel`. The API process never imports this package.
"""
