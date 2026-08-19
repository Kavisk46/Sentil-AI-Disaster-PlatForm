"""Evaluates `app.incident`'s real narrative-generation pipeline for
groundedness, completeness, and unsupported-claim rate — always via the
existing `MockLLMProvider` (`app.incident.mock_provider`), never a real
LLM API. Every test in this package works with no external API key and
no network access, matching `app.incident`'s own testing discipline.
"""
