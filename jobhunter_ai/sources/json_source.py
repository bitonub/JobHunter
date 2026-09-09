from __future__ import annotations

from pathlib import Path

from ..io import load_json
from ..models import Job
from .base import JobSource


class JsonJobSource(JobSource):
    """Load job listings from a JSON file."""

    def __init__(self, path: str | Path = "data/sample_jobs.json") -> None:
        self.path = Path(path)

    def fetch_jobs(self) -> list[Job]:
        return [Job.from_dict(item) for item in load_json(self.path)]
