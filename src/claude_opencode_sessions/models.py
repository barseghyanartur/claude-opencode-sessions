"""Backend-independent data model."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

__all__ = ["Message", "Part", "Session", "format_model"]


def format_model(value: Any) -> str | None:
    """Render a model reference as ``provider/model``.

    opencode stores models either as a JSON string/object
    (``{"id": ..., "providerID": ...}``) or as separate fields.
    """
    if value is None or value == "":
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped.startswith("{"):
            return stripped
        try:
            value = json.loads(stripped)
        except ValueError:
            return stripped
    if isinstance(value, dict):
        model = value.get("id") or value.get("modelID")
        provider = value.get("providerID")
        if model and provider:
            return f"{provider}/{model}"
        if model:
            return str(model)
    return None


@dataclass
class Session:
    id: str
    title: str
    directory: str
    project_id: str | None = None
    parent_id: str | None = None
    time_created: int | None = None
    time_updated: int | None = None
    time_archived: int | None = None
    agent: str | None = None
    model: str | None = None
    version: str | None = None
    message_count: int | None = None
    cost: float | None = None
    tokens_input: int | None = None
    tokens_output: int | None = None
    origin: str = "sqlite"

    @property
    def is_subagent(self) -> bool:
        return bool(self.parent_id)

    @property
    def is_archived(self) -> bool:
        return bool(self.time_archived)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["is_subagent"] = self.is_subagent
        data["is_archived"] = self.is_archived
        return data


@dataclass
class Part:
    kind: str
    text: str = ""
    tool: str | None = None
    tool_input: Any = None
    tool_output: str | None = None
    status: str | None = None
    title: str | None = None
    files: list[str] = field(default_factory=list)
    synthetic: bool = False


@dataclass
class Message:
    id: str
    role: str
    time_created: int | None = None
    parts: list[Part] = field(default_factory=list)
    seq: int | None = None
    model: str | None = None
    agent: str | None = None
    error: str | None = None
    tokens: dict[str, Any] | None = None
    cost: float | None = None
