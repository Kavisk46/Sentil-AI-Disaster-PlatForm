import pytest
from app.incident.fallback import build_fallback_narrative
from app.incident.mock_provider import MockLLMProvider
from app.incident.validator import parse_llm_output

from research.experiments.llm.evaluation import (
    completeness_score,
    contains_supplied_facts,
    is_grounded,
    unsupported_claim_rate,
)
from research.experiments.llm.fixtures import empty_context, spec_example_context


def test_valid_mock_output_is_grounded() -> None:
    context = spec_example_context()
    raw = MockLLMProvider("valid").generate_incident_summary(context)
    narrative = parse_llm_output(raw)

    assert narrative is not None
    assert is_grounded(narrative, context) is True


def test_valid_mock_output_correctly_reflects_supplied_facts() -> None:
    """Verifies the generated output actually states the real numbers
    from the fixture (severely_damaged=14, route risk=0.31) — not just
    that it avoids inventing anything."""
    context = spec_example_context()
    raw = MockLLMProvider("valid").generate_incident_summary(context)
    narrative = parse_llm_output(raw)

    assert narrative is not None
    assert contains_supplied_facts(narrative, ["14", "0.31"])


def test_unsupported_claim_behavior_is_not_grounded() -> None:
    context = spec_example_context()
    raw = MockLLMProvider("unsupported_claim").generate_incident_summary(context)
    narrative = parse_llm_output(raw)

    assert narrative is not None
    assert is_grounded(narrative, context) is False


@pytest.mark.parametrize(
    "expected_substring",
    ["casualt", "closure", "closed", "rain"],
)
def test_deterministic_fallback_never_states_forbidden_topics(expected_substring: str) -> None:
    """The mock's `unsupported_claim` behavior DOES mention casualties/road
    closure/weather (that's what makes it a useful fixture for
    `test_unsupported_claim_behavior_is_not_grounded` above) — this test
    instead confirms the deterministic fallback that replaces a rejected
    narrative (`app.incident.fallback.build_fallback_narrative`, the real
    production fallback) never mentions any forbidden topic, since it can
    only ever state what's actually in the context."""
    context = spec_example_context()
    fallback_narrative = build_fallback_narrative(context)
    haystack = " ".join(
        [
            fallback_narrative.priority_area,
            fallback_narrative.route_summary,
            *fallback_narrative.key_findings,
            *fallback_narrative.limitations,
        ]
    ).lower()
    assert expected_substring not in haystack


def test_unsupported_claim_rate_over_a_mixed_batch() -> None:
    context = spec_example_context()
    grounded_raw = MockLLMProvider("valid").generate_incident_summary(context)
    ungrounded_raw = MockLLMProvider("unsupported_claim").generate_incident_summary(context)
    grounded_narrative = parse_llm_output(grounded_raw)
    ungrounded_narrative = parse_llm_output(ungrounded_raw)
    assert grounded_narrative is not None and ungrounded_narrative is not None

    rate = unsupported_claim_rate(
        [(grounded_narrative, context), (ungrounded_narrative, context)]
    )

    assert rate == pytest.approx(0.5)


def test_unsupported_claim_rate_requires_at_least_one_pair() -> None:
    with pytest.raises(ValueError, match="at least one"):
        unsupported_claim_rate([])


def test_completeness_score_for_a_fully_populated_narrative() -> None:
    context = spec_example_context()
    raw = MockLLMProvider("valid").generate_incident_summary(context)
    narrative = parse_llm_output(raw)
    assert narrative is not None
    assert completeness_score(narrative) == 1.0


def test_completeness_score_for_the_empty_context_fallback() -> None:
    """With nothing available, the deterministic fallback should
    correctly report 'Information unavailable.' for both required
    fields — completeness 0.0, not a fabricated summary."""
    narrative = build_fallback_narrative(empty_context())
    assert completeness_score(narrative) == 0.0


def test_contains_supplied_facts_is_false_when_a_fact_is_missing() -> None:
    context = spec_example_context()
    raw = MockLLMProvider("valid").generate_incident_summary(context)
    narrative = parse_llm_output(raw)
    assert narrative is not None
    assert contains_supplied_facts(narrative, ["this-number-was-never-supplied-999"]) is False
