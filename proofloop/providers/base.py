"""Provider interface.

ProofLoop's offline foundation ships no network client. A Provider is just a
prompt-in/text-out object; the only implementation here is the FakeProvider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class ProviderResponse(BaseModel):
    text: str
    role: str = ""
    provider: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class Provider(ABC):
    """Base class. Implementations must never be constructed with secrets."""

    name: str = "provider"

    def __init__(self) -> None:
        self.call_count: int = 0

    @abstractmethod
    def generate(self, prompt: str, role: str = "", **kwargs: Any) -> ProviderResponse:
        """Return a response for ``prompt``. May raise ProviderError."""

    def reset(self) -> None:
        self.call_count = 0
