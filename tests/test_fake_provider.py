"""The FakeProvider: deterministic, offline, and able to fail on purpose."""

from __future__ import annotations

import sys

import pytest

from proofloop.providers import (
    FakeProvider,
    ProviderRefusal,
    ProviderTimeout,
)
from proofloop.registry import available_providers, get_provider
from proofloop.providers.errors import ProviderUnavailable


def test_canned_output_is_deterministic() -> None:
    provider = FakeProvider(responses={"planner": "always the same"})
    first = provider.generate("prompt", role="planner")
    second = provider.generate("prompt", role="planner")
    assert first.text == second.text == "always the same"


def test_call_count_and_metadata() -> None:
    provider = FakeProvider(metadata={"scenario": "unit"})
    assert provider.call_count == 0
    response = provider.generate("prompt", role="judge")
    assert provider.call_count == 1
    assert response.metadata["offline"] is True
    assert response.metadata["network"] is False
    assert response.metadata["scenario"] == "unit"
    assert response.provider == "fake"
    provider.reset()
    assert provider.call_count == 0


def test_timeout_simulation() -> None:
    provider = FakeProvider(simulate_timeout=True)
    with pytest.raises(ProviderTimeout):
        provider.generate("prompt", role="planner")
    assert provider.call_count == 1


def test_refusal_simulation() -> None:
    provider = FakeProvider(simulate_refusal=True)
    with pytest.raises(ProviderRefusal):
        provider.generate("prompt", role="critic")


def test_failure_can_target_a_single_role() -> None:
    provider = FakeProvider(simulate_timeout=True, fail_on_role="judge")
    assert provider.generate("prompt", role="planner").text
    with pytest.raises(ProviderTimeout):
        provider.generate("prompt", role="judge")


def test_prompts_are_recorded_for_inspection() -> None:
    provider = FakeProvider()
    provider.generate("hello world", role="planner")
    assert provider.prompts == [("planner", "hello world")]


def test_no_model_sdk_is_imported() -> None:
    """The offline foundation must not pull in a live model SDK."""
    FakeProvider().generate("prompt", role="planner")
    forbidden = {"openai", "anthropic", "google.generativeai", "cohere", "mistralai"}
    assert forbidden.isdisjoint(sys.modules)


def test_registry_exposes_only_the_fake_provider() -> None:
    assert available_providers() == ["fake"]
    assert isinstance(get_provider("fake"), FakeProvider)


def test_registry_rejects_unknown_provider() -> None:
    with pytest.raises(ProviderUnavailable):
        get_provider("openai")
