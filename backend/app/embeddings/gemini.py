from __future__ import annotations

import logging

from app.embeddings.base import EmbeddingProvider

logger = logging.getLogger("jistory.embeddings")


class GeminiEmbeddingProvider(EmbeddingProvider):
    """Optional remote embeddings. Conversation text leaves the machine."""

    def __init__(self, api_key: str, model_name: str) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self.dimensions = 768
        self._client = None

    def _client_or_raise(self):
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured.")
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        client = self._client_or_raise()
        vectors: list[list[float]] = []
        for text in texts:
            response = client.models.embed_content(model=self.model_name, contents=text)
            embedding = getattr(response, "embeddings", None) or getattr(response, "embedding", None)
            if embedding is None:
                raise RuntimeError("Gemini embedding response was empty.")
            values = embedding[0].values if isinstance(embedding, list) else embedding.values
            vectors.append([float(x) for x in values])
        return vectors
