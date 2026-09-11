from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .filters import evaluate_job
from .io import load_json, write_json
from .job_requirements import extract_job_requirements
from .job_quality import evaluate_email_job_quality
from .matcher import match_job
from .models import Profile
from .diagnostics import build_diagnostic_summary
from .review_queue import (
    build_review_queue_diagnostics,
    evaluate_review_candidate,
    load_review_terms,
    write_review_queue,
)
from .sources import JobSource
from .storage import JobStateStatus, JobStateStore
from .tailor import build_tailored_cv


def run_pipeline(
    profile_path: str,
    jobs_source: JobSource,
    output_dir: str,
    threshold: float = 60.0,
    preferences_path: str | None = None,
    job_terms_path: str | None = None,
    state_store: JobStateStore | None = None,
) -> dict:
    profile = Profile.from_dict(load_json(profile_path))
    jobs = jobs_source.fetch_jobs()
    preferences = load_json(preferences_path) if preferences_path else {
        "allowed_employment_types": ["internship", "part-time", "trainee", "apprenticeship", "student"],
        "allow_unknown_employment_type": False,
        "excluded_keywords": ["senior", "sr.", "lead", "manager", "director"],
    }
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    alerts = []
    filtered_out = []
    review_queue = []
    review_diagnostic_codes = []
    review_terms = None
    new_jobs = 0
    previously_seen_jobs = 0
    skipped_alerted_jobs = 0
    for raw_job in jobs:
        job = extract_job_requirements(raw_job, terms_path=job_terms_path)
        quality_result = evaluate_email_job_quality(job)
        if state_store is None:
            new_jobs += 1
        else:
            stored_state = state_store.get(job)
            if stored_state is None:
                new_jobs += 1
                state_store.record(job, JobStateStatus.SEEN)
            else:
                previously_seen_jobs += 1
                if stored_state.status == JobStateStatus.ALERTED.value:
                    skipped_alerted_jobs += 1
                    continue
                state_store.record(job, stored_state.status, stored_state.score)

        if quality_result.applicable and not quality_result.accepted:
            filtered_out.append(
                {
                    "job": asdict(job),
                    "filter": quality_result.to_filter_dict(job),
                    "quality": quality_result.to_dict(),
                }
            )
            if state_store is not None:
                state_store.record(job, JobStateStatus.DISCARDED)
            continue

        filter_result = evaluate_job(job, preferences)
        if not filter_result.accepted:
            filtered_out.append({"job": asdict(job), "filter": filter_result.to_dict()})
            if review_terms is None:
                review_terms = load_review_terms(preferences, job_terms_path)
            review_decision = evaluate_review_candidate(
                job,
                filter_result,
                review_terms,
                preferences,
            )
            if review_decision.entry is not None:
                review_queue.append(review_decision.entry)
            if review_decision.diagnostic_code is not None:
                review_diagnostic_codes.append(review_decision.diagnostic_code)
            if state_store is not None:
                state_store.record(
                    job,
                    JobStateStatus.REVIEWABLE
                    if review_decision.entry
                    else JobStateStatus.DISCARDED,
                )
            continue
        result = match_job(profile, job, threshold=threshold)
        record = {
            "job": asdict(job),
            "analysis": result.to_dict(),
            "filter": filter_result.to_dict(),
        }
        if quality_result.applicable:
            record["quality"] = quality_result.to_dict()
        if result.compatible:
            if state_store is not None:
                state_store.record(job, JobStateStatus.COMPATIBLE, result.score)
            tailored = build_tailored_cv(profile, job, result)
            cv_path = output / f"cv_adaptado_{job.id}.md"
            cv_path.write_text(tailored.markdown, encoding="utf-8")
            record["tailored_cv_path"] = str(cv_path)
            record["traceability"] = tailored.selected_evidence
        elif state_store is not None:
            state_store.record(job, JobStateStatus.REVIEWABLE, result.score)
        alerts.append(record)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "threshold": threshold,
        "total_jobs": len(jobs),
        "new_jobs": new_jobs,
        "previously_seen_jobs": previously_seen_jobs,
        "skipped_alerted_jobs": skipped_alerted_jobs,
        "eligible_jobs": len(alerts),
        "compatible_jobs": sum(item["analysis"]["compatible"] for item in alerts),
        "filtered_out_jobs": len(filtered_out),
        "review_queue_jobs": len(review_queue),
        "review_queue_diagnostics": build_review_queue_diagnostics(
            review_diagnostic_codes
        ),
        "diagnostics": build_diagnostic_summary(filtered_out, alerts, threshold),
        "preferences": preferences,
        "alerts": alerts,
        "review_queue": review_queue,
        "filtered_out": filtered_out,
    }
    write_json(output / "alerts.json", report)
    write_review_queue(output / "review_queue.md", review_queue)
    return report
