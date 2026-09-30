"""Backend-independent data model."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

__all__ = ["Message", "Part", "Session"]


@dataclass
class Session:
    id: str
    title: str
    directory: str
    project_id: str | None = None
    time_created: int | None = None
    time_updated: int | None = None
    agent: str | None = None
    model: str | None = None
    version: str | None = None
    source: str | None = None
    message_count: int | None = None
    origin: str = "rollout"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Part:
    kind: str
    text: str = ""
    tool: str | None = None
    tool_input: Any = None
    tool_output: str | None = None
    status: str | None = None
    files: list[str] = field(default_factory=list)
    synthetic: bool = False


@dataclass
class Message:
    id: str
    role: str
    time_created: int | None = None
    parts: list[Part] = field(default_factory=list)
    seq: int | None = None
