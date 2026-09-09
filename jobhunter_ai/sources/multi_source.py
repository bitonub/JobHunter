from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from ..models import Job
from .base import JobSource


class MultiJobSource(JobSource):
    """Combine several job sources while removing duplicate listings."""

    def __init__(self, sources: Iterable[JobSource]) -> None:
        self.sources = list(sources)

    def fetch_jobs(self) -> list[Job]:
        jobs: list[Job] = []
        seen: set[tuple[str, str]] = set()
        for source in self.sources:
            for job in source.fetch_jobs():
                key = self._deduplication_key(job)
                if key in seen:
                    continue
                seen.add(key)
                jobs.append(job)
        return jobs

    @classmethod
    def _deduplication_key(cls, job: Job) -> tuple[str, str]:
        if job.url.strip():
            return "url", job.url.strip()
        return "title-company", cls._normalize(f"{job.title} {job.company}")

    @staticmethod
    def _normalize(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value.lower())
        without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
        return re.sub(r"\s+", " ", without_accents).strip()
