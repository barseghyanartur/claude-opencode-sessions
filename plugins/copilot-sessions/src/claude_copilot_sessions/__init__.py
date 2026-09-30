"""Import GitHub Copilot CLI sessions into Claude Code, scoped to the current repo."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("claude-copilot-sessions")
except PackageNotFoundError:  # running from a source checkout, e.g. as the plugin
    __version__ = "0+source"

__all__ = ["__version__"]
