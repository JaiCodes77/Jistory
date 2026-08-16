from __future__ import annotations

import logging

from app.embeddings.base import EmbeddingProvider
from app.embeddings.hash import HashEmbeddingProvider

logger = logging.getLogger("jistory.embeddings")


class LocalEmbeddingProvider(EmbeddingProvider):
    """ONNX embeddings that run entirely on this machine.

    Conversation text is not sent to a remote API.
    The model is downloaded once on first use.
    """

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        self.model_name = model_name
        self.dimensions = 384
        self._model = None
        self._fallback: EmbeddingProvider | None = None

    def _load(self):
        if self._model is not None:
            return self._model
        try:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self.model_name)
            logger.info("Loaded local embedding model %s", self.model_name)
            return self._model
        except Exception as exc:
            logger.warning(
                "Local embedding model unavailable (%s); using hash fallback. "
                "Semantic search quality will be limited.",
                exc,
            )
            self._fallback = HashEmbeddingProvider()
            self.model_name = self._fallback.model_name
            return None

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load()
        if model is None:
            assert self._fallback is not None
            return self._fallback.embed_documents(texts)
        vectors = []
        for item in model.embed(texts):
            vectors.append([float(x) for x in item])
        return vectors
