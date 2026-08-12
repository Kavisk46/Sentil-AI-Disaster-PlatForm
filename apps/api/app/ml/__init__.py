"""Damage-intelligence ML architecture.

Deliberately separated from `app/api` and `app/services`: this package has
no FastAPI import anywhere in it, so the inference pipeline is testable and
(eventually) deployable independently of the HTTP layer.

    Image -> Preprocessor -> Model -> Postprocessor -> DamageAnalysis

See `apps/api/README.md` ("ML Architecture") for the full picture and
`docs/architecture/ai-engine.md` for how this fits the platform overall.
No trained model exists yet (Milestone 3A is architecture only) — see
`app/ml/model.py`.

`app.ml.datasets` (Milestone 3B) is the dataset pipeline that will
eventually produce that trained model — see `app/ml/datasets/__init__.py`.
"""
