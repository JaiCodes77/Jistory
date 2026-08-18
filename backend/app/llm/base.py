from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass


@dataclass
class ChatTurn:
    role: str
    content: str


class LLMProvider(ABC):
    """Answer generation. Implementations must not log prompts or secrets."""

    model_name: str

    @abstractmethod
    def generate(
        self,
        *,
        system: str,
        prompt: str,
        history: list[ChatTurn],
    ) -> str:
        """Return model text. Raise on failure."""

    def generate_stream(
        self,
        *,
        system: str,
        prompt: str,
        history: list[ChatTurn],
    ) -> Iterator[str]:
        """Yield answer text as it arrives. Default sends the full completion once."""
        text = self.generate(system=system, prompt=prompt, history=history)
        if text:
            yield text
