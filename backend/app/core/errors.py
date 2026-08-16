class AppError(Exception):
    """User-facing application error that routes map to HTTP responses."""

    def __init__(
        self,
        message: str,
        code: str = "error",
        status_code: int = 400,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
