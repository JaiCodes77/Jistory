from abc import ABC, abstractmethod
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
