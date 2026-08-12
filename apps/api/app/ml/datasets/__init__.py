"""Dataset pipeline for training the damage-detection model.

Separate in concern from the rest of `app.ml` (which is about serving
inference) and entirely separate from the FastAPI application — nothing
here is reachable through any route, and no route imports it.

    Dataset -> ImageSample -> BuildingAnnotation -> DamageClass

`base.DisasterDamageDataset` is the dataset-agnostic interface;
`xbd.XbdDataset` is its only implementation today, for the xBD/xView2
dataset. See `apps/api/README.md` ("Dataset pipeline") for what xBD is,
why it fits SentinelAI, and where to place it locally — datasets are never
downloaded automatically and never committed to Git.
"""
