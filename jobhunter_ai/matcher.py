from __future__ import annotations

import re

from .models import Job, MatchResult, Profile


def _normalize(value: str) -> str:
    value = value.lower().replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", value).strip()


def _contains(text: str, term: str) -> bool:
    normalized_text = _normalize(text)
    normalized_term = _normalize(term)
    if not normalized_term:
        return False
    return normalized_term in normalized_text


def _evidence_for(profile: Profile, term: str) -> list[str]:
    results: list[str] = []
    for category, values in profile.skills.items():
        if _contains(category, term):
            evidence = profile.evidence.get(f"skill:{category}")
            if evidence:
                results.append(f"{evidence.section}: {evidence.source_text}")
        for value in values:
            if _contains(value, term):
                evidence = profile.evidence.get(f"skill:{value}")
                if evidence:
                    results.append(f"{evidence.section}: {evidence.source_text}")

    for index, item in enumerate(profile.experience):
        for bullet_index, bullet in enumerate(item.bullets):
            if _contains(bullet, term):
                results.append(f"Experiencia {index + 1}, punto {bullet_index + 1}: {bullet}")

    for item in profile.projects:
        if _contains(item.name, term) or _contains(item.description, term) or any(
            _contains(keyword, term) for keyword in item.keywords
        ):
            results.append(f"Proyecto {item.name}: {item.description}")

    for certification in profile.certifications:
        if _contains(certification, term):
            results.append(f"Certificación: {certification}")
    return list(dict.fromkeys(results))


def match_job(profile: Profile, job: Job, threshold: float = 60.0) -> MatchResult:
    if not any((job.required_skills, job.preferred_skills, job.keywords)):
        return MatchResult(
            job_id=job.id,
            score=0.0,
            compatible=False,
            matched_required=[],
            missing_required=[],
            matched_preferred=[],
            missing_preferred=[],
            matched_keywords=[],
            evidence_by_skill={},
        )

    searchable = profile.searchable_text()
    matched_required = [term for term in job.required_skills if _contains(searchable, term)]
    missing_required = [term for term in job.required_skills if term not in matched_required]
    matched_preferred = [term for term in job.preferred_skills if _contains(searchable, term)]
    missing_preferred = [term for term in job.preferred_skills if term not in matched_preferred]
    matched_keywords = [term for term in job.keywords if _contains(searchable, term)]

    required_ratio = len(matched_required) / len(job.required_skills) if job.required_skills else 1.0
    preferred_ratio = len(matched_preferred) / len(job.preferred_skills) if job.preferred_skills else 1.0
    keyword_ratio = len(matched_keywords) / len(job.keywords) if job.keywords else 1.0
    score = round((required_ratio * 60) + (preferred_ratio * 25) + (keyword_ratio * 15), 2)

    evidence_by_skill = {
        term: _evidence_for(profile, term)
        for term in [*matched_required, *matched_preferred, *matched_keywords]
    }
    return MatchResult(
        job_id=job.id,
        score=score,
        compatible=score >= threshold,
        matched_required=matched_required,
        missing_required=missing_required,
        matched_preferred=matched_preferred,
        missing_preferred=missing_preferred,
        matched_keywords=matched_keywords,
        evidence_by_skill=evidence_by_skill,
    )
