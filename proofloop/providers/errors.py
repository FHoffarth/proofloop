"""Provider failure modes. All of them fail closed at the gate."""

from __future__ import annotations


class ProviderError(Exception):
    """Base class for anything a provider can go wrong with."""


class ProviderTimeout(ProviderError):
    """The provider did not answer within its budget."""


class ProviderRefusal(ProviderError):
    """The provider declined to answer."""


class ProviderUnavailable(ProviderError):
    """The provider is not usable in this environment (e.g. offline mode)."""
