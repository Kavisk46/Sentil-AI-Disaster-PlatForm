"""Shared research infrastructure: the result schema, reproducibility
metadata capture, metrics (including Pareto analysis and a real paired
t-test), result storage, report/figure generation, and latency
measurement. Nothing in this package is specific to routing/damage/
hazard/LLM evaluation — those live in `research.experiments.*` and import
from here.
"""
