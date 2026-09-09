from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Evidence:
    """A claim that can be traced back to the original CV."""

    claim: str
    section: str
    source_text: str


@dataclass
class Experience:
    company: str
    title: str
    dates: str
    location: str
    bullets: list[str]


@dataclass
class Project:
    name: str
    description: str
    keywords: list[str]


@dataclass
class Profile:
    name: str
    location: str
    contact: dict[str, str]
    summary: str
    education: list[dict[str, str]]
    experience: list[Experience]
    projects: list[Project]
    certifications: list[str]
    skills: dict[str, list[str]]
    evidence: dict[str, Evidence] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Profile":
        return cls(
            name=data["name"],
            location=data["location"],
            contact=data["contact"],
            summary=data["summary"],
            education=data["education"],
            experience=[Experience(**item) for item in data["experience"]],
            projects=[Project(**item) for item in data["projects"]],
            certifications=data["certifications"],
            skills=data["skills"],
            evidence={key: Evidence(**value) for key, value in data.get("evidence", {}).items()},
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def searchable_text(self) -> str:
        parts = [self.name, self.location, self.summary]
        parts.extend(item["degree"] for item in self.education)
        parts.extend(item["school"] for item in self.education)
        parts.extend(skill for values in self.skills.values() for skill in values)
        for item in self.experience:
            parts.extend([item.company, item.title, *item.bullets])
        for item in self.projects:
            parts.extend([item.name, item.description, *item.keywords])
        parts.extend(self.certifications)
        return " ".join(parts)


@dataclass
class Job:
    id: str
    title: str
    company: str
    location: str
    url: str
    description: str
    required_skills: list[str]
    preferred_skills: list[str]
    keywords: list[str]
    source: str = "manual"
    employment_type: str = "unknown"
    schedule: str = "unknown"
    experience_level: str = "unknown"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Job":
        return cls(
            id=data["id"],
            title=data["title"],
            company=data["company"],
            location=data.get("location", "No especificada"),
            url=data["url"],
            description=data["description"],
            required_skills=data.get("required_skills", []),
            preferred_skills=data.get("preferred_skills", []),
            keywords=data.get("keywords", []),
            source=data.get("source", "manual"),
            employment_type=data.get("employment_type", "unknown"),
            schedule=data.get("schedule", "unknown"),
            experience_level=data.get("experience_level", "unknown"),
        )


@dataclass
class MatchResult:
    job_id: str
    score: float
    compatible: bool
    matched_required: list[str]
    missing_required: list[str]
    matched_preferred: list[str]
    missing_preferred: list[str]
    matched_keywords: list[str]
    evidence_by_skill: dict[str, list[str]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TailoredCV:
    job_id: str
    markdown: str
    selected_evidence: dict[str, list[str]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
