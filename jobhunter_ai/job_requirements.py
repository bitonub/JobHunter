from __future__ import annotations

import re
import unicodedata
from dataclasses import replace
from pathlib import Path

from .io import load_json
from .models import Job


DEFAULT_JOB_TERMS_PATH = Path(__file__).resolve().parent.parent / "data" / "job_terms.json"
_REQUIRED_MARKERS = ("required", "requisitos", "must have", "indispensable", "obligatorio")
_PREFERRED_MARKERS = ("preferred", "deseable", "nice to have", "plus", "valorable")
_SENTENCE_BOUNDARIES = ".!?;\n"


def extract_job_requirements(job: Job, terms_path: str | Path | None = None) -> Job:
    """Return a copy of a job with technical terms classified from its text."""

    terms = _load_terms(terms_path or DEFAULT_JOB_TERMS_PATH)
    text = _normalize(f"{job.title} {job.description}")
    required: list[str] = []
    preferred: list[str] = []
    keywords: list[str] = []

    for term in terms:
        normalized_term = _normalize(term)
        if not normalized_term:
            continue
        pattern = re.compile(rf"(?<!\w){re.escape(normalized_term)}(?!\w)")
        classifications = [
            _classify_occurrence(text, match.start(), match.end())
            for match in pattern.finditer(text)
        ]
        classification = _strongest_classification(classifications)
        if classification == "required":
            required.append(term)
        elif classification == "preferred":
            preferred.append(term)
        elif classification == "keyword":
            keywords.append(term)

    return replace(
        job,
        required_skills=_merge_terms(job.required_skills, required),
        preferred_skills=_merge_terms(job.preferred_skills, preferred),
        keywords=_merge_terms(job.keywords, keywords),
    )


def _load_terms(path: str | Path) -> list[str]:
    data = load_json(path)
    values = data.get("terms", []) if isinstance(data, dict) else data
    if not isinstance(values, list):
        raise ValueError("job terms must be a JSON list or an object with a 'terms' list")
    return [str(value).strip() for value in values if str(value).strip()]


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.lower())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_accents).strip()


def _marker_matches(text: str, markers: tuple[str, ...]) -> list[re.Match[str]]:
    matches: list[re.Match[str]] = []
    for marker in markers:
        normalized_marker = _normalize(marker)
        pattern = re.compile(rf"(?<!\w){re.escape(normalized_marker)}(?!\w)")
        matches.extend(pattern.finditer(text))
    return matches


def _classify_occurrence(text: str, start: int, end: int) -> str | None:
    left = max(
        (text.rfind(boundary, 0, start) + 1 for boundary in _SENTENCE_BOUNDARIES),
        default=0,
    )
    right_candidates = [
        text.find(boundary, end)
        for boundary in _SENTENCE_BOUNDARIES
        if text.find(boundary, end) >= 0
    ]
    right = min(right_candidates, default=len(text))
    segment = text[left:right]

    candidates = [
        (match.start() + left, "required")
        for match in _marker_matches(segment, _REQUIRED_MARKERS)
    ] + [
        (match.start() + left, "preferred")
        for match in _marker_matches(segment, _PREFERRED_MARKERS)
    ]
    if candidates:
        return min(candidates, key=lambda item: abs(item[0] - start))[1]
    return "keyword"


def _strongest_classification(classifications: list[str | None]) -> str | None:
    for classification in ("required", "preferred", "keyword"):
        if classification in classifications:
            return classification
    return None


def _merge_terms(existing: list[str], extracted: list[str]) -> list[str]:
    result = list(existing)
    seen = {_normalize(term) for term in result}
    for term in extracted:
        normalized = _normalize(term)
        if normalized not in seen:
            result.append(term)
            seen.add(normalized)
    return result
