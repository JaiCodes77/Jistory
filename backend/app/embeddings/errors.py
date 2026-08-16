class EmbeddingUnavailableError(Exception):
    """Raised when the configured embedding provider cannot run.

    Hash embeddings are tests-only. Production must fail clearly instead of
    silently degrading to hash vectors.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
