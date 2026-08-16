from __future__ import annotations

import logging

from app.embeddings.base import EmbeddingProvider
from app.embeddings.errors import EmbeddingUnavailableError
from app.embeddings.runtime import set_embedding_status

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

    def _load(self):
        if self._model is not None:
            return self._model
        set_embedding_status(
            "downloading",
            f"Downloading {self.model_name} (first run). This can take a minute.",
        )
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            message = (
                "Local embeddings require FastEmbed. Install backend dependencies with `uv sync`."
            )
            set_embedding_status("unavailable", message)
            raise EmbeddingUnavailableError(message) from exc

        try:
            self._model = TextEmbedding(model_name=self.model_name)
        except Exception as exc:
            message = (
                "Could not download or load the local embedding model. "
                "Check your network and try parsing again."
            )
            logger.warning("Local embedding model unavailable")
            set_embedding_status("unavailable", message)
            raise EmbeddingUnavailableError(message) from exc

        logger.info("Loaded local embedding model %s", self.model_name)
        set_embedding_status("ready", f"Local embedding model {self.model_name} is ready.")
        return self._model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load()
        vectors = []
        for item in model.embed(texts):
            vectors.append([float(x) for x in item])
        return vectors
