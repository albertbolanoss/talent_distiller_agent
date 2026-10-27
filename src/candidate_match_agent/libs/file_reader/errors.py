"""Errors raised by the file_reader library."""


class UnsupportedFileTypeError(ValueError):
    """Raised when a file's extension has no registered reader."""

    def __init__(self, extension: str, supported: list[str]) -> None:
        self.extension = extension
        self.supported = supported
        super().__init__(
            f"Unsupported file type '{extension or '(none)'}'. "
            f"Supported extensions: {', '.join(supported)}"
        )
