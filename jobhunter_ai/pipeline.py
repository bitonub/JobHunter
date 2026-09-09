from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .filters import evaluate_job
from .io import load_json, write_json
from .matcher import match_job
from .models import Job, Profile
from .tailor import build_tailored_cv


def run_pipeline(
    profile_path: str,
    jobs_path: str,
    output_dir: str,
    threshold: float = 60.0,
    preferences_path: str | None = None,
) -> dict:
    profile = Profile.from_dict(load_json(profile_path))
    jobs = [Job.from_dict(item) for item in load_json(jobs_path)]
    preferences = load_json(preferences_path) if preferences_path else {
        "allowed_employment_types": ["internship", "part-time", "trainee", "apprenticeship", "student"],
        "allow_unknown_employment_type": False,
        "excluded_keywords": ["senior", "sr.", "lead", "manager", "director"],
    }
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    alerts = []
    filtered_out = []
    for job in jobs:
        filter_result = evaluate_job(job, preferences)
        if not filter_result.accepted:
            filtered_out.append({"job": asdict(job), "filter": filter_result.to_dict()})
            continue
        result = match_job(profile, job, threshold=threshold)
        record = {
            "job": asdict(job),
            "analysis": result.to_dict(),
            "filter": filter_result.to_dict(),
        }
        if result.compatible:
            tailored = build_tailored_cv(profile, job, result)
            cv_path = output / f"cv_adaptado_{job.id}.md"
            cv_path.write_text(tailored.markdown, encoding="utf-8")
            record["tailored_cv_path"] = str(cv_path)
            record["traceability"] = tailored.selected_evidence
        alerts.append(record)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "threshold": threshold,
        "total_jobs": len(jobs),
        "eligible_jobs": len(jobs) - len(filtered_out),
        "compatible_jobs": sum(item["analysis"]["compatible"] for item in alerts),
        "filtered_out_jobs": len(filtered_out),
        "preferences": preferences,
        "alerts": alerts,
        "filtered_out": filtered_out,
    }
    write_json(output / "alerts.json", report)
    return report
