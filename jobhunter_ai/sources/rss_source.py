from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from ..models import Job
from .base import JobSource


class RssJobSource(JobSource):
    """Load job listings from an RSS or Atom feed."""

    def __init__(
        self,
        feed_url: str | Path,
        source: str = "rss",
        timeout: float = 15.0,
    ) -> None:
        self.feed_url = str(feed_url)
        self.source = source
        self.timeout = timeout

    def fetch_jobs(self) -> list[Job]:
        root = ET.fromstring(self._read_feed())
        entries = self._find_entries(root)
        return [self._to_job(entry, index) for index, entry in enumerate(entries, start=1)]

    def _read_feed(self) -> bytes:
        scheme = urlparse(self.feed_url).scheme.lower()
        if scheme in {"http", "https", "file"}:
            with urlopen(self.feed_url, timeout=self.timeout) as response:
                return response.read()
        return Path(self.feed_url).read_bytes()

    @classmethod
    def _find_entries(cls, root: ET.Element) -> list[ET.Element]:
        root_name = cls._local_name(root.tag)
        entry_names = {"entry"} if root_name == "feed" else {"item"}
        if root_name not in {"rss", "feed"}:
            entry_names = {"item", "entry"}
        return [
            element
            for element in root.iter()
            if element is not root and cls._local_name(element.tag) in entry_names
        ]

    def _to_job(self, entry: ET.Element, index: int) -> Job:
        title = self._find_text(entry, {"title"})
        url = self._find_link(entry)
        entry_id = self._find_text(entry, {"guid", "id"}) or url or f"rss-entry-{index}"
        company = self._find_text(entry, {"company", "employer", "organization", "publisher", "author"})
        location = self._find_text(entry, {"location", "job_location", "city", "region"})
        description = self._find_text(entry, {"description", "summary", "content", "encoded"})

        return Job(
            id=entry_id,
            title=title,
            company=company or "No especificada",
            location=location or "No especificada",
            url=url,
            description=description,
            source=self.source,
            required_skills=[],
            preferred_skills=[],
            keywords=[],
        )

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1].lower().replace("-", "_")

    @classmethod
    def _find_text(cls, element: ET.Element, names: set[str]) -> str:
        for child in element.iter():
            if child is element or cls._local_name(child.tag) not in names:
                continue
            value = " ".join("".join(child.itertext()).split())
            if value:
                return value
        return ""

    @classmethod
    def _find_link(cls, element: ET.Element) -> str:
        candidates: list[str] = []
        for child in element.iter():
            if child is element or cls._local_name(child.tag) != "link":
                continue
            href = child.attrib.get("href", "").strip()
            value = href or " ".join("".join(child.itertext()).split())
            if not value:
                continue
            if child.attrib.get("rel", "alternate").lower() == "alternate":
                return value
            candidates.append(value)
        return candidates[0] if candidates else ""
