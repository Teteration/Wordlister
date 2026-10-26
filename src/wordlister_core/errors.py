"""Expected application errors with safe, user-facing messages."""


class WordlisterError(Exception):
    """Base class for errors that the CLI can report without a traceback."""


class InvalidTargetError(WordlisterError):
    """Raised when a target URL violates the HTTP input contract."""


class FetchError(WordlisterError):
    """A bounded HTTP operation failed in an expected way."""

    def __init__(self, target: str, code: str, message: str) -> None:
        super().__init__(message)
        self.target = target
        self.code = code
        self.message = message
