"""The LLM provider abstraction.

`LLMProvider` is the seam a real model (OpenAI, Anthropic, a local
Hugging Face model, or the deterministic template provider) plugs into —
the same Protocol-based swap pattern already used throughout this
codebase (`DamageModel`, `BuildingLocalizer`, `RoadNetworkSource`, ...).
Nothing in the API layer or `IncidentIntelligenceService` hard-codes a
specific provider; swapping one for another is a one-line DI change (see
`app/api/deps.py`).
"""

from typing import Protocol

from app.incident.schemas import IncidentContext


class LLMProviderError(RuntimeError):
    """Raised when a provider fails to produce output at all (network
    failure, API error response, ...). `IncidentIntelligenceService`
    always catches this and falls back to the deterministic narrative —
    it never propagates to the API layer."""


class LLMTimeoutError(LLMProviderError):
    """Raised when a provider call exceeds its configured timeout."""


class LLMProvider(Protocol):
    def generate_incident_summary(self, context: IncidentContext) -> str:
        """Returns raw text — expected to be a JSON object matching
        `LLMNarrativeOutput`, but not guaranteed to be: parsing and
        validation are the caller's job (`app.incident.validator`), not
        this method's. Raises `LLMProviderError`/`LLMTimeoutError` on
        failure; never returns a fabricated or partial briefing itself.
        """
        ...
