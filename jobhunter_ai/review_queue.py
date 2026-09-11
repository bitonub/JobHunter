from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .filters import EMPLOYMENT_ALIASES, FilterResult, contains_term, normalize_text
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
_ALLOWED_WORK_MODES = {"remote", "hybrid", "on-site"}
_DEFAULT_ALLOWED_LOCATIONS = (
    "Monterrey",
    "Apodaca",
    "San Nicolás de los Garza",
    "Guadalupe",
    "General Escobedo",
    "Escobedo",
    "Santa Catarina",
    "San Pedro Garza García",
    "García",
    "Juárez",
    "Cadereyta Jiménez",
    "Santiago",
    "Salinas Victoria",
    "El Carmen",
    "Pesquería",
    "Ciénega de Flores",
)
_DIAGNOSTIC_REASONS = {
    "outside_allowed_location": (
        "Ubicación fuera de Monterrey y el área metropolitana de Nuevo León."
    ),
    "full_time_detected": (
        "Se detectó una señal explícita de tiempo completo en título o descripción."
    ),
    "insufficient_work_mode_or_location": (
        "No hay evidencia suficiente de modalidad o ubicación."
    ),
}


@dataclass(frozen=True)
class ReviewQueueDecision:
    entry: dict[str, str] | None = None
    diagnostic_code: str | None = None


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


def evaluate_review_candidate(
    job: Job,
    filter_result: FilterResult,
    technical_terms: list[str],
    preferences: dict[str, Any],
) -> ReviewQueueDecision:
    """Select safe unknown-type jobs without weakening the main filters."""

    if (
        _is_missing(job.title)
        or _is_missing(job.company)
        or not _is_valid_url(job.url)
    ):
        return ReviewQueueDecision()
    if not _is_it_related(job, filter_result, technical_terms):
        return ReviewQueueDecision()
    if (
        filter_result.employment_type == "full-time"
        or _contains_full_time_signal(job)
    ):
        return ReviewQueueDecision(diagnostic_code="full_time_detected")
    if filter_result.accepted or filter_result.employment_type != "unknown":
        return ReviewQueueDecision()
    unknown_reasons = [
        reason
        for reason in filter_result.reasons
        if reason.startswith(_UNKNOWN_EMPLOYMENT_REASON_PREFIX)
    ]
    if not unknown_reasons:
        return ReviewQueueDecision()

    location = " ".join(job.location.split())
    if _is_missing(location) or filter_result.work_mode not in _ALLOWED_WORK_MODES:
        return ReviewQueueDecision(
            diagnostic_code="insufficient_work_mode_or_location"
        )
    if filter_result.work_mode in {"hybrid", "on-site"}:
        configured_locations = preferences.get(
            "onsite_hybrid_allowed_locations",
            _DEFAULT_ALLOWED_LOCATIONS,
        )
        configured_location_keys = {
            normalize_text(term) for term in configured_locations
        }
        metropolitan_locations = [
            term
            for term in _DEFAULT_ALLOWED_LOCATIONS
            if normalize_text(term) in configured_location_keys
        ]
        if not any(
            contains_term(location, term) for term in metropolitan_locations
        ):
            return ReviewQueueDecision(diagnostic_code="outside_allowed_location")

    ignored_reasons = {
        *unknown_reasons,
        *(
            reason
            for reason in filter_result.reasons
            if reason.startswith(
                ("Modalidad no compatible:", "Ubicación no compatible")
            )
        ),
    }
    if any(reason not in ignored_reasons for reason in filter_result.reasons):
        return ReviewQueueDecision()

    entry = {
        "title": " ".join(job.title.split()),
        "company": " ".join(job.company.split()),
        "location": location,
        "url": job.url.strip(),
        "reason": _REVIEW_REASON,
    }
    return ReviewQueueDecision(entry=entry)


def build_review_queue_diagnostics(codes: list[str]) -> dict[str, object]:
    return {
        code: {
            "count": codes.count(code),
            "reason": reason,
        }
        for code, reason in _DIAGNOSTIC_REASONS.items()
    }


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


def _contains_full_time_signal(job: Job) -> bool:
    text = f"{job.title} {job.description}"
    return any(
        contains_term(text, term) for term in EMPLOYMENT_ALIASES["full-time"]
    )


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
