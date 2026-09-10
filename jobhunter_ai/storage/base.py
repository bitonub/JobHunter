from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ..models import Job


class JobStateStatus(str, Enum):
    SEEN = "visto"
    DISCARDED = "descartado"
    REVIEWABLE = "revisable"
    COMPATIBLE = "compatible"
    ALERTED = "alertado"


@dataclass(frozen=True)
class JobStateKey:
    identifier_hash: str
    source: str
    link_hash: str


@dataclass(frozen=True)
class StoredJobState:
    key: JobStateKey
    first_seen: str
    last_seen: str
    status: str
    score: float | None


class JobStateStore(ABC):
    @abstractmethod
    def get(self, job: Job) -> StoredJobState | None:
        """Return the current state for this exact job identity."""

    @abstractmethod
    def record(
        self,
        job: Job,
        status: JobStateStatus | str,
        score: float | None = None,
    ) -> StoredJobState:
        """Insert or update a processing state, excluding alert confirmation."""

    @abstractmethod
    def mark_alerted(
        self,
        job: Job,
        score: float | None = None,
    ) -> StoredJobState:
        """Confirm that an external alert channel delivered this job successfully."""

    @abstractmethod
    def close(self) -> None:
        """Release storage resources."""


def build_job_state_key(job: Job) -> JobStateKey:
    normalized_link = _normalize_link(job.url)
    identifier = job.id.strip() or normalized_link or f"{job.title.strip()}\n{job.company.strip()}"
    return JobStateKey(
        identifier_hash=_sha256(identifier),
        source=job.source.strip().lower() or "unknown",
        link_hash=_sha256(normalized_link) if normalized_link else "",
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_link(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    parts = urlsplit(value)
    query = [
        (key, item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in {"fbclid", "gclid", "mc_cid", "mc_eid"}
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            path,
            urlencode(sorted(query)),
            "",
        )
    )
