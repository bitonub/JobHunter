from __future__ import annotations

from .models import Job, MatchResult, Profile, TailoredCV


def _bullet_relevance(bullet: str, terms: list[str]) -> int:
    lowered = bullet.lower()
    return sum(term.lower() in lowered for term in terms)


def build_tailored_cv(profile: Profile, job: Job, result: MatchResult) -> TailoredCV:
    """Build an ATS-friendly Markdown CV from verified profile facts only."""

    terms = [*result.matched_required, *result.matched_preferred, *result.matched_keywords]
    selected_evidence: dict[str, list[str]] = {}

    relevant_experience: list[tuple[int, int, str]] = []
    for experience_index, experience in enumerate(profile.experience):
        company_matches: list[tuple[int, int, str]] = []
        for bullet_index, bullet in enumerate(experience.bullets):
            relevance = _bullet_relevance(bullet, terms)
            if relevance:
                company_matches.append((relevance, bullet_index, bullet))
                relevant_experience.append((relevance, bullet_index, bullet))
        selected_evidence[experience.company] = [
            bullet for _, _, bullet in sorted(company_matches, reverse=True)
        ][:4]

    relevant_projects = [
        project for project in profile.projects
        if any(term.lower() in (project.name + " " + project.description).lower() for term in terms)
        or any(term.lower() in " ".join(project.keywords).lower() for term in terms)
    ]
    if not relevant_projects:
        relevant_projects = profile.projects[:2]

    skill_lines = []
    for category, values in profile.skills.items():
        selected = [value for value in values if any(term.lower() in value.lower() or value.lower() in term.lower() for term in terms)]
        if selected:
            skill_lines.append(f"- **{category}:** {', '.join(selected)}")
    if not skill_lines:
        skill_lines = [f"- **{category}:** {', '.join(values)}" for category, values in profile.skills.items()]

    lines = [
        f"# {profile.name}",
        f"{profile.location} | " + " | ".join(profile.contact.values()),
        "",
        "## Perfil profesional",
        profile.summary,
        "",
        "## Competencias clave",
        *skill_lines,
        "",
        "## Experiencia profesional",
    ]
    for experience in profile.experience:
        lines.extend([
            f"### {experience.company} - {experience.title}",
            f"{experience.location} | {experience.dates}",
        ])
        chosen = selected_evidence.get(experience.company, [])
        if not chosen:
            chosen = experience.bullets[:2]
        lines.extend(f"- {bullet}" for bullet in chosen)
        lines.append("")

    lines.append("## Proyectos técnicos")
    for project in relevant_projects:
        lines.append(f"- **{project.name}:** {project.description}")
    lines.extend(["", "## Educación"])
    for education in profile.education:
        lines.append(f"- **{education['school']}:** {education['degree']} ({education['dates']})")
    lines.extend(["", "## Certificaciones"])
    lines.extend(f"- {certification}" for certification in profile.certifications)
    lines.extend([
        "",
        "---",
        f"CV adaptado para: {job.title} - {job.company}",
        "Cada elemento anterior proviene de información verificada del CV original.",
    ])

    selected_evidence["job"] = [
        f"Vacante: {job.title} - {job.company}",
        f"Compatibilidad calculada: {result.score}%",
    ]
    return TailoredCV(job_id=job.id, markdown="\n".join(lines), selected_evidence=selected_evidence)
