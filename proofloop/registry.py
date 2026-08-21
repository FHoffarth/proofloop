"""Provider registry.

The offline foundation registers exactly one provider. Nothing here imports a
model SDK, and there is no dynamic import path a caller can steer.
"""

from __future__ import annotations

from typing import Any, Callable

from .providers import FakeProvider, Provider, ProviderUnavailable

ProviderFactory = Callable[..., Provider]

_REGISTRY: dict[str, ProviderFactory] = {}


def register_provider(name: str, factory: ProviderFactory) -> None:
    _REGISTRY[name] = factory


def available_providers() -> list[str]:
    return sorted(_REGISTRY)


def get_provider(name: str = "fake", **kwargs: Any) -> Provider:
    try:
        factory = _REGISTRY[name]
    except KeyError:
        raise ProviderUnavailable(
            f"unknown provider {name!r}; available: {', '.join(available_providers())}"
        ) from None
    return factory(**kwargs)


register_provider("fake", FakeProvider)
