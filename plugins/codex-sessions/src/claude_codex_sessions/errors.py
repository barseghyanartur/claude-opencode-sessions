"""Exceptions shared by the reader and the CLI."""

__all__ = [
    "BackendError",
    "CodexSessionsError",
    "NotFoundError",
    "SessionsDirNotFoundError",
]


class CodexSessionsError(Exception):
    """Base class; ``exit_code`` is used by the CLI."""

    exit_code = 1


class NotFoundError(CodexSessionsError):
    """A session reference did not match anything."""

    exit_code = 2


class SessionsDirNotFoundError(CodexSessionsError):
    """No Codex ``sessions`` directory could be located."""

    exit_code = 3


class BackendError(CodexSessionsError):
    """Sessions could not be read."""

    exit_code = 4
