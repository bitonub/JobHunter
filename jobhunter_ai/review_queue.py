from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .filters import FilterResult, contains_term
from .io import load_json
from .job_quality import is_synthetic_url
from .job_requirements import DEFAULT_JOB_TERMS_PATH
from .models import Job


_MISSING_VALUES = {
    "",
    "unknown",
    "not specified",
    "no description available",
    "description not available",
    "no especificado",
    "no especificada",
    "sin descripción",
    "sin descripcion",
    "sin especificar",
    "confidential",
    "confidencial",
}
_UNKNOWN_EMPLOYMENT_REASON_PREFIX = "Tipo de empleo no compatible: unknown."
_REVIEW_REASON = "Tipo de empleo desconocido; requiere revisión manual."


def load_review_terms(
    preferences: dict[str, Any],
    terms_path: str | Path | None = None,
) -> list[str]:
    """Load public technical terms used only to identify review candidates."""

    catalog = load_json(terms_path or DEFAULT_JOB_TERMS_PATH)
    catalog_terms = catalog.get("terms", []) if isinstance(catalog, dict) else catalog
    values = [
        *preferences.get("it_terms", []),
        *preferences.get("priority_terms", []),
        *(catalog_terms if isinstance(catalog_terms, list) else []),
    ]
    return list(
        dict.fromkeys(str(value).strip() for value in values if str(value).strip())
    )


def build_review_entry(
    job: Job,
    filter_result: FilterResult,
    technical_terms: list[str],
) -> dict[str, str] | None:
    """Return a privacy-minimal entry when only employment type needs review."""

    if filter_result.accepted or filter_result.employment_type != "unknown":
        return None
    unknown_reasons = [
        reason
        for reason in filter_result.reasons
        if reason.startswith(_UNKNOWN_EMPLOYMENT_REASON_PREFIX)
    ]
    if not unknown_reasons:
        return None
    if any(reason not in unknown_reasons for reason in filter_result.reasons):
        return None
    if _is_missing(job.title) or _is_missing(job.company) or not _is_valid_url(job.url):
        return None
    if not _is_it_related(job, filter_result, technical_terms):
        return None

    entry = {
        "title": " ".join(job.title.split()),
        "company": " ".join(job.company.split()),
    }
    if not _is_missing(job.location):
        entry["location"] = " ".join(job.location.split())
    entry["url"] = job.url.strip()
    entry["reason"] = _REVIEW_REASON
    return entry


def write_review_queue(path: str | Path, entries: list[dict[str, str]]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Cola de revisión manual", "", f"Vacantes pendientes: {len(entries)}"]
    if not entries:
        lines.extend(["", "No hay vacantes pendientes de revisión."])
    for entry in entries:
        lines.extend(
            [
                "",
                f"## {_markdown_text(entry['title'])}",
                "",
                f"- Empresa: {_markdown_text(entry['company'])}",
            ]
        )
        if entry.get("location"):
            lines.append(f"- Ubicación: {_markdown_text(entry['location'])}")
        lines.extend(
            [
                f"- Enlace original: <{entry['url']}>",
                f"- Motivo: {_markdown_text(entry['reason'])}",
            ]
        )
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _is_it_related(
    job: Job,
    filter_result: FilterResult,
    technical_terms: list[str],
) -> bool:
    if filter_result.it_matches or filter_result.priority_matches:
        return True
    text = " ".join(
        [
            job.title,
            job.description,
            *job.required_skills,
            *job.preferred_skills,
            *job.keywords,
        ]
    )
    return any(contains_term(text, term) for term in technical_terms)


def _is_missing(value: str) -> bool:
    return " ".join(value.lower().split()).strip(" .:-") in _MISSING_VALUES


def _is_valid_url(value: str) -> bool:
    normalized = value.strip()
    if not normalized or any(character in normalized for character in "\r\n<>"):
        return False
    try:
        parsed = urlsplit(normalized)
    except ValueError:
        return False
    return (
        parsed.scheme.lower() in {"http", "https"}
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and not is_synthetic_url(normalized)
    )


def _markdown_text(value: str) -> str:
    normalized = " ".join(value.split())
    for character in "\\`*_{}[]<>#|":
        normalized = normalized.replace(character, f"\\{character}")
    return normalized
