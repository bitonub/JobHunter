from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from .models import Job


EMPLOYMENT_ALIASES = {
    "internship": [
        "internship program",
        "internship",
        "intern",
        "practicante",
        "práctica",
        "prácticas",
        "practica",
        "practicas",
        "becario",
        "becaria",
        "pasantía",
        "pasantia",
    ],
    "part-time": ["part-time", "part time", "medio tiempo", "half-time"],
    "trainee": ["trainee", "graduate program", "entry-level trainee"],
    "apprenticeship": ["apprenticeship", "apprentice", "aprendiz", "aprendizaje"],
    "student": ["student job", "student position", "student", "estudiante"],
    "full-time": ["full-time", "full time", "tiempo completo", "jornada completa"],
    "contract": ["contractor", "contract", "freelance", "por contrato"],
}

WORK_MODE_ALIASES = {
    "hybrid": ["hybrid", "híbrido", "híbrida", "hibrido", "hibrida"],
    "remote": ["remote", "remoto", "remota", "teletrabajo"],
    "on-site": ["on-site", "on site", "onsite", "presencial"],
}


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value).lower())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_accents).strip()


def contains_term(text: str, term: str) -> bool:
    """Match a normalized term without accepting it inside a larger word."""

    normalized_text = normalize_text(text)
    normalized_term = normalize_text(term)
    if not normalized_term:
        return False
    pattern = rf"(?<!\w){re.escape(normalized_term)}(?!\w)"
    return re.search(pattern, normalized_text) is not None


def _classify_alias(text: str, aliases_by_category: dict[str, list[str]]) -> str:
    for category, aliases in aliases_by_category.items():
        if any(contains_term(text, alias) for alias in aliases):
            return category
    return "unknown"


def classify_employment_type(job: Job) -> str:
    explicit = normalize_text(job.employment_type)
    if explicit and explicit != "unknown":
        classified = _classify_alias(explicit, EMPLOYMENT_ALIASES)
        return explicit if classified == "unknown" else classified

    text = f"{job.title} {job.description} {job.schedule}"
    # A full-time declaration must win over entry-level wording such as "intern".
    if any(contains_term(text, alias) for alias in EMPLOYMENT_ALIASES["full-time"]):
        return "full-time"
    return _classify_alias(text, EMPLOYMENT_ALIASES)


def classify_work_mode(job: Job) -> str:
    # Jobicy's configured endpoint is specifically a remote-jobs API.
    if normalize_text(job.source) == "jobicy":
        return "remote"
    return _classify_alias(
        f"{job.title} {job.description} {job.location}",
        WORK_MODE_ALIASES,
    )


def _term_present(text: str, term: str) -> bool:
    # Keep the short English acronym from matching the ordinary pronoun "it".
    if term == "IT":
        return re.search(r"(?<!\w)IT(?!\w)", text) is not None
    if normalize_text(term).endswith("."):
        return contains_term(text, term) or contains_term(text, term.rstrip("."))
    return contains_term(text, term)


def _matched_terms(text: str, terms: list[str]) -> list[str]:
    matches: list[str] = []
    seen: set[str] = set()
    for term in terms:
        key = normalize_text(term)
        if key not in seen and _term_present(text, term):
            matches.append(term)
            seen.add(key)
    return matches


@dataclass
class FilterResult:
    job_id: str
    accepted: bool
    employment_type: str
    work_mode: str
    reasons: list[str]
    matched_preferences: list[str]
    priority_matches: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "accepted": self.accepted,
            "employment_type": self.employment_type,
            "work_mode": self.work_mode,
            "reasons": self.reasons,
            "matched_preferences": self.matched_preferences,
            "priority_matches": self.priority_matches,
        }


def evaluate_job(job: Job, preferences: dict[str, Any]) -> FilterResult:
    employment_type = classify_employment_type(job)
    work_mode = classify_work_mode(job)
    allowed_types = [normalize_text(value) for value in preferences.get("allowed_employment_types", [])]
    allowed_work_modes = [normalize_text(value) for value in preferences.get("allowed_work_modes", [])]
    excluded_seniority = preferences.get(
        "excluded_seniority",
        preferences.get("excluded_keywords", []),
    )
    reasons: list[str] = []
    matched_preferences: list[str] = []

    if employment_type in allowed_types:
        matched_preferences.append(f"tipo: {employment_type}")
    elif employment_type == "unknown" and preferences.get("allow_unknown_employment_type", False):
        matched_preferences.append("tipo: desconocido permitido por configuración")
    else:
        reasons.append(
            f"Tipo de empleo no compatible: {employment_type}. "
            f"Permitidos: {', '.join(allowed_types)}."
        )

    # Seniority is intentionally derived only from title and experience_level.
    seniority_text = f"{job.title} {job.experience_level}"
    found_seniority = _matched_terms(seniority_text, list(excluded_seniority))
    if found_seniority:
        reasons.append(f"Palabra o nivel excluido: {', '.join(found_seniority)}.")

    if allowed_work_modes:
        if work_mode in allowed_work_modes:
            matched_preferences.append(f"modalidad: {work_mode}")
        elif work_mode == "unknown" and preferences.get("allow_unknown_work_mode", False):
            matched_preferences.append("modalidad: desconocida permitida por configuración")
        else:
            reasons.append(
                f"Modalidad no compatible: {work_mode}. "
                f"Permitidas: {', '.join(allowed_work_modes)}."
            )

        if work_mode == "remote" and preferences.get("allow_remote_any_location", False):
            matched_preferences.append("ubicación: cualquiera por modalidad remota")
        elif work_mode in {"hybrid", "on-site"}:
            allowed_locations = list(preferences.get("onsite_hybrid_allowed_locations", []))
            matching_locations = _matched_terms(job.location, allowed_locations)
            if matching_locations:
                matched_preferences.append(f"ubicación permitida: {matching_locations[0]}")
            else:
                reasons.append(
                    f"Ubicación no compatible para {work_mode}: {job.location}. "
                    "Solo se permite Nuevo León y su área metropolitana."
                )

    searchable_job_text = " ".join(
        [
            job.title,
            job.description,
            *job.required_skills,
            *job.preferred_skills,
            *job.keywords,
        ]
    )
    priority_matches = _matched_terms(
        searchable_job_text,
        list(preferences.get("priority_terms", [])),
    )
    if priority_matches:
        matched_preferences.extend(f"prioridad: {term}" for term in priority_matches)

    if preferences.get("reject_non_it", False):
        it_terms = list(preferences.get("it_terms", []))
        technical_matches = _matched_terms(searchable_job_text, it_terms)
        if technical_matches or priority_matches:
            matched_preferences.append("área: TI")
        else:
            reasons.append("Área no compatible: no se detectaron términos de TI.")

    return FilterResult(
        job_id=job.id,
        accepted=not reasons,
        employment_type=employment_type,
        work_mode=work_mode,
        reasons=reasons,
        matched_preferences=matched_preferences,
        priority_matches=priority_matches,
    )
