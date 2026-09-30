"""Import opencode sessions into Claude Code, scoped to the current repository."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("claude-opencode-sessions")
except PackageNotFoundError:  # running from a source checkout, e.g. as the plugin
    __version__ = "0+source"

__all__ = ["__version__"]
