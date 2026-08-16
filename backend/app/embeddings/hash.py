from __future__ import annotations

import hashlib
import math

from app.embeddings.base import EmbeddingProvider

DIM = 384


class HashEmbeddingProvider(EmbeddingProvider):
    """Deterministic local embeddings for tests only.

    This is not a semantic model. Production uses LocalEmbeddingProvider and
    must not fall back here.
    """

    model_name = "hash-384"
    dimensions = DIM

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [_embed_one(text) for text in texts]


def _embed_one(text: str) -> list[float]:
    vec = [0.0] * DIM
    if not text:
        return vec
    tokens = text.lower().split()
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
        for i in range(0, 16, 2):
            idx = int.from_bytes(digest[i : i + 2], "little") % DIM
            vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]
