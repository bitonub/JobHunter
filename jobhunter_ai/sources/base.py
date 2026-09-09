from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Job


class JobSource(ABC):
    """Interface for retrieving job listings from an external source."""

    @abstractmethod
    def fetch_jobs(self) -> list[Job]:
        """Return job listings as domain objects."""
