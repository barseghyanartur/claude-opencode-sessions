"""Exceptions shared by the backends and the CLI."""

__all__ = [
    "BackendError",
    "DatabaseNotFoundError",
    "NotFoundError",
    "OpencodeSessionsError",
    "SchemaError",
]


class OpencodeSessionsError(Exception):
    """Base class; ``exit_code`` is used by the CLI."""

    exit_code = 1


class NotFoundError(OpencodeSessionsError):
    """A session reference did not match anything."""

    exit_code = 2


class DatabaseNotFoundError(OpencodeSessionsError):
    """No opencode database could be located."""

    exit_code = 3


class SchemaError(OpencodeSessionsError):
    """The database exists but does not look like a supported opencode DB."""

    exit_code = 3


class BackendError(OpencodeSessionsError):
    """No backend could serve the request."""

    exit_code = 4
