"""Exceptions shared by the reader and the CLI."""

__all__ = [
    "BackendError",
    "CopilotSessionsError",
    "NotFoundError",
    "SessionsDirNotFoundError",
]


class CopilotSessionsError(Exception):
    """Base class; ``exit_code`` is used by the CLI."""

    exit_code = 1


class NotFoundError(CopilotSessionsError):
    """A session reference did not match anything."""

    exit_code = 2


class SessionsDirNotFoundError(CopilotSessionsError):
    """No Copilot CLI ``session-state`` directory could be located."""

    exit_code = 3


class BackendError(CopilotSessionsError):
    """Sessions could not be read."""

    exit_code = 4
