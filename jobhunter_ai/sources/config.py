from __future__ import annotations

from pathlib import Path

from ..io import load_json
from .base import JobSource
from .email_alert_source import EmailAlertJobSource
from .gmail_label_source import GmailLabelJobSource
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
        if source_type == "gmail":
            token_path = definition.get("token_path") or definition.get("token")
            if not token_path:
                raise ValueError(f"Gmail source #{index} must define 'token_path'")
            sources.append(
                GmailLabelJobSource(
                    token_path,
                    definition.get("allowed_sender_domains"),
                    label_name=str(definition.get("label", "JobHunter/Alertas")),
                    max_messages=int(definition.get("max_messages", 50)),
                )
            )
            continue
        location = definition.get("path") or definition.get("url")
        if not location:
            raise ValueError(f"source #{index} must define 'path' or 'url'")
        if source_type == "json":
            sources.append(JsonJobSource(location))
        elif source_type in {"email", "email-alert", "eml"}:
            provider = str(definition.get("provider", "")).strip() or None
            sources.append(EmailAlertJobSource(location, provider=provider))
        elif source_type == "jobicy":
            sources.append(JobicyApiSource(location))
        elif source_type in {"rss", "atom"}:
            source_name = str(definition.get("source", "rss")).strip() or "rss"
            sources.append(RssJobSource(location, source=source_name))
        else:
            raise ValueError(f"unsupported source type at source #{index}: {source_type}")
    return MultiJobSource(sources)
