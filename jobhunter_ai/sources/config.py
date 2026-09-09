from __future__ import annotations

from pathlib import Path

from ..io import load_json
from .base import JobSource
from .json_source import JsonJobSource
from .jobicy_source import JobicyApiSource
from .multi_source import MultiJobSource
from .rss_source import RssJobSource


def load_configured_source(path: str | Path) -> MultiJobSource:
    """Build a combined source from a JSON list of source definitions."""

    definitions = load_json(path)
    if not isinstance(definitions, list):
        raise ValueError("sources configuration must be a JSON list")

    sources: list[JobSource] = []
    for index, definition in enumerate(definitions, start=1):
        if not isinstance(definition, dict):
            raise ValueError(f"source #{index} must be a JSON object")
        source_type = str(definition.get("type", "")).strip().lower()
        location = definition.get("path") or definition.get("url")
        if not location:
            raise ValueError(f"source #{index} must define 'path' or 'url'")
        if source_type == "json":
            sources.append(JsonJobSource(location))
        elif source_type == "jobicy":
            sources.append(JobicyApiSource(location))
        elif source_type in {"rss", "atom"}:
            source_name = str(definition.get("source", "rss")).strip() or "rss"
            sources.append(RssJobSource(location, source=source_name))
        else:
            raise ValueError(f"unsupported source type at source #{index}: {source_type}")
    return MultiJobSource(sources)
