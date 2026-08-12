"""The one real, network-calling `LLMProvider` implemented this milestone
— isolated entirely behind the `LLMProvider` Protocol, exactly like
`OverpassRoadNetworkSource` (`app.roads.osm_source`) isolates the one
real, network-calling `RoadNetworkSource`. Never invoked by the test
suite, by default configuration (`Settings.LLM_PROVIDER` defaults to
`"deterministic"`), or by any code path that doesn't explicitly opt in.

Uses the standard library's `urllib.request` rather than adding a new
HTTP client dependency for one call site — the same choice
`OverpassRoadNetworkSource` already made.

The API key is read once, from `Settings.LLM_API_KEY` (itself a
`pydantic.SecretStr`, sourced only from the environment — never
hardcoded), and is **never logged**: it appears only in the
`x-api-key` request header, never in any log statement, exception
message, or `repr()` in this module.

Other providers (OpenAI, a local Hugging Face model, ...) would follow
this exact same shape — implement `generate_incident_summary()`, raise
`LLMProviderError`/`LLMTimeoutError` on failure, and register in
`app/api/deps.py`'s `get_llm_provider()` — without any change to
`IncidentIntelligenceService` or the API layer.
"""

import json
import urllib.request
from urllib.error import URLError

from pydantic import SecretStr

from app.incident.prompt import SYSTEM_PROMPT, build_user_message
from app.incident.provider import LLMProviderError, LLMTimeoutError
from app.incident.schemas import IncidentContext

_ANTHROPIC_MESSAGES_ENDPOINT = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"
_MAX_OUTPUT_TOKENS = 1024


class AnthropicLLMProvider:
    def __init__(
        self,
        api_key: SecretStr,
        model: str,
        timeout_seconds: float,
        endpoint: str = _ANTHROPIC_MESSAGES_ENDPOINT,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._endpoint = endpoint

    def generate_incident_summary(self, context: IncidentContext) -> str:
        payload = {
            "model": self._model,
            "max_tokens": _MAX_OUTPUT_TOKENS,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": build_user_message(context)}],
        }
        request = urllib.request.Request(
            self._endpoint,
            data=json.dumps(payload).encode(),
            method="POST",
            headers={
                "content-type": "application/json",
                "anthropic-version": _ANTHROPIC_VERSION,
                "x-api-key": self._api_key.get_secret_value(),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                body = json.loads(response.read())
        except TimeoutError as exc:
            raise LLMTimeoutError(
                f"Anthropic API call exceeded the {self._timeout_seconds}s timeout."
            ) from exc
        except (URLError, ValueError) as exc:
            # Deliberately generic: never includes the API key, and never
            # echoes raw response bodies that might contain it either.
            raise LLMProviderError(f"Anthropic API call failed: {exc.__class__.__name__}") from exc

        return _extract_text(body)


def _extract_text(response_body: object) -> str:
    """Anthropic's Messages API returns `{"content": [{"type": "text", "text": "..."}]}`."""
    if not isinstance(response_body, dict):
        raise LLMProviderError("Anthropic API returned an unexpected response shape.")
    content = response_body.get("content")
    if not isinstance(content, list) or not content:
        raise LLMProviderError("Anthropic API response had no content blocks.")
    first_block = content[0]
    text = first_block.get("text") if isinstance(first_block, dict) else None
    if not isinstance(text, str):
        raise LLMProviderError("Anthropic API response's first content block had no text.")
    return text
