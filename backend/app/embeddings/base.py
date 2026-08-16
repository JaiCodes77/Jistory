from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    model_name: str
    dimensions: int

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed one or more documents. Never log the input text."""

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed_documents([text])
        return vectors[0] if vectors else []
