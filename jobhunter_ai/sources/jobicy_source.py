from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ..models import Job
from .base import JobSource


DEFAULT_JOBICY_API_URL = "https://jobicy.com/api/v2/remote-jobs?count=200&tag=python"


class JobicyApiSource(JobSource):
    """Load remote jobs from Jobicy's public JSON API."""

    def __init__(self, api_url: str = DEFAULT_JOBICY_API_URL, timeout: float = 15.0) -> None:
        self.api_url = api_url
        self.timeout = timeout

    def fetch_jobs(self) -> list[Job]:
        payload = self._read_payload()
        records = payload.get("jobs", []) if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            raise ValueError("Jobicy API response must contain a 'jobs' list")
        return [self._to_job(record, index) for index, record in enumerate(records, start=1)]

    def _read_payload(self) -> object:
        scheme = urlparse(self.api_url).scheme.lower()
        if scheme in {"http", "https"}:
            request = Request(self.api_url, headers={"Accept": "application/json"})
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        return json.loads(Path(self.api_url).read_text(encoding="utf-8"))

    @classmethod
    def _to_job(cls, record: object, index: int) -> Job:
        if not isinstance(record, dict):
            raise ValueError(f"Jobicy record #{index} must be a JSON object")

        url = cls._text(record.get("url"))
        job_id = cls._text(record.get("id")) or cls._text(record.get("jobSlug")) or url or f"jobicy-{index}"
        return Job(
            id=job_id,
            title=cls._text(record.get("jobTitle")),
            company=cls._text(record.get("companyName")) or "No especificada",
            location=cls._text(record.get("jobGeo")) or "No especificada",
            url=url,
            description=cls._text(record.get("jobExcerpt")),
            required_skills=[],
            preferred_skills=[],
            keywords=[],
            source="jobicy",
            employment_type=cls._employment_type(record.get("jobType")),
            experience_level=cls._text(record.get("jobLevel")) or "unknown",
        )

    @staticmethod
    def _text(value: object) -> str:
        if isinstance(value, list):
            value = value[0] if value else ""
        return str(value).strip() if value is not None else ""

    @classmethod
    def _employment_type(cls, value: object) -> str:
        employment_type = cls._text(value)
        canonical = {
            "internship": "internship",
            "part time": "part-time",
            "part-time": "part-time",
            "full time": "full-time",
            "full-time": "full-time",
        }
        return canonical.get(employment_type.lower(), employment_type or "unknown")
