from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from .models import Job


EMPLOYMENT_ALIASES = {
    "internship": [
        "internship", "intern", "practicante", "prácticas", "practicas",
        "becario", "becaria", "pasantía", "pasantia",
    ],
    "part-time": ["part-time", "part time", "medio tiempo", "half-time"],
    "trainee": ["trainee", "graduate program", "entry-level trainee", "aprendiz"],
    "apprenticeship": ["apprenticeship", "apprentice", "aprendizaje"],
    "student": ["student job", "student position", "estudiante"],
    "full-time": ["full-time", "full time", "tiempo completo", "jornada completa"],
    "contract": ["contractor", "contract", "freelance", "por contrato"],
}


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.lower())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_accents).strip()


def classify_employment_type(job: Job) -> str:
    explicit = normalize_text(job.employment_type)
    if explicit and explicit != "unknown":
        return explicit

    text = normalize_text(f"{job.title} {job.description}")
    for category, aliases in EMPLOYMENT_ALIASES.items():
        if any(normalize_text(alias) in text for alias in aliases):
            return category
    return "unknown"


@dataclass
class FilterResult:
    job_id: str
    accepted: bool
    employment_type: str
    reasons: list[str]
    matched_preferences: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "accepted": self.accepted,
            "employment_type": self.employment_type,
            "reasons": self.reasons,
            "matched_preferences": self.matched_preferences,
        }


def evaluate_job(job: Job, preferences: dict[str, Any]) -> FilterResult:
    employment_type = classify_employment_type(job)
    allowed_types = [normalize_text(value) for value in preferences.get("allowed_employment_types", [])]
    excluded_keywords = [normalize_text(value) for value in preferences.get("excluded_keywords", [])]
    text = normalize_text(f"{job.title} {job.description}")
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

    found_excluded = [keyword for keyword in excluded_keywords if keyword in text]
    if found_excluded:
        reasons.append(f"Palabra o nivel excluido: {', '.join(found_excluded)}.")

    return FilterResult(
        job_id=job.id,
        accepted=not reasons,
        employment_type=employment_type,
        reasons=reasons,
        matched_preferences=matched_preferences,
    )
