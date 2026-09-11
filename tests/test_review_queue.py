import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jobhunter_ai.models import Job
from jobhunter_ai.pipeline import run_pipeline
from jobhunter_ai.sources import JobSource


class StaticJobSource(JobSource):
    def __init__(self, jobs: list[Job]) -> None:
        self.jobs = jobs

    def fetch_jobs(self) -> list[Job]:
        return self.jobs


def make_job(**overrides) -> Job:
    values = {
        "id": "synthetic-review-job",
        "title": "Cloud Operations Analyst",
        "company": "Synthetic Technology Lab",
        "location": "Monterrey, Nuevo León",
        "url": "https://www.linkedin.com/jobs/view/9000000001",
        "description": "Monitor Python automation and Linux infrastructure.",
        "required_skills": [],
        "preferred_skills": [],
        "keywords": [],
        "source": "synthetic",
        "employment_type": "unknown",
        "schedule": "unknown",
        "experience_level": "entry-level",
    }
    values.update(overrides)
    return Job(**values)


class ManualReviewQueueTests(unittest.TestCase):
    def run_jobs(self, jobs: list[Job], output: str) -> dict:
        return run_pipeline(
            "data/profile.example.json",
            StaticJobSource(jobs),
            output,
            preferences_path="data/preferences.json",
            job_terms_path="data/job_terms.json",
        )

    def test_unknown_technical_job_is_queued_without_matching_cv_or_alert(self):
        job = make_job()
        with (
            tempfile.TemporaryDirectory() as output,
            patch("jobhunter_ai.pipeline.match_job") as matcher,
            patch("jobhunter_ai.pipeline.build_tailored_cv") as tailor,
        ):
            report = self.run_jobs([job], output)
            markdown = (Path(output) / "review_queue.md").read_text(encoding="utf-8")
            generated_cvs = list(Path(output).glob("cv_adaptado_*.md"))

        matcher.assert_not_called()
        tailor.assert_not_called()
        self.assertEqual(report["eligible_jobs"], 0)
        self.assertEqual(report["compatible_jobs"], 0)
        self.assertEqual(report["alerts"], [])
        self.assertEqual(report["review_queue_jobs"], 1)
        self.assertEqual(generated_cvs, [])
        self.assertIn(job.title, markdown)
        self.assertIn(job.company, markdown)
        self.assertIn(job.url, markdown)
        self.assertNotIn(job.description, markdown)

    def test_json_queue_contains_only_allowed_fields(self):
        with tempfile.TemporaryDirectory() as output:
            report = self.run_jobs([make_job()], output)
            saved_report = json.loads(
                (Path(output) / "alerts.json").read_text(encoding="utf-8")
            )

        expected_fields = {"title", "company", "location", "url", "reason"}
        self.assertEqual(set(report["review_queue"][0]), expected_fields)
        self.assertEqual(saved_report["review_queue"], report["review_queue"])
        self.assertEqual(
            report["review_queue"][0]["reason"],
            "Tipo de empleo desconocido; requiere revisión manual.",
        )

    def test_missing_location_is_omitted_from_queue_entry(self):
        with tempfile.TemporaryDirectory() as output:
            report = self.run_jobs(
                [make_job(location="No especificada")],
                output,
            )

        self.assertEqual(
            set(report["review_queue"][0]),
            {"title", "company", "url", "reason"},
        )

    def test_non_it_unknown_job_is_not_queued(self):
        job = make_job(
            title="Editorial Coordinator",
            description="Coordinate articles and publication calendars.",
            required_skills=["copy editing"],
        )
        with tempfile.TemporaryDirectory() as output:
            report = self.run_jobs([job], output)

        self.assertEqual(report["review_queue"], [])

    def test_unknown_job_with_another_filter_rejection_is_not_queued(self):
        job = make_job(title="Senior Cloud Operations Analyst")
        with tempfile.TemporaryDirectory() as output:
            report = self.run_jobs([job], output)

        self.assertEqual(report["review_queue"], [])

    def test_synthetic_or_missing_job_data_is_not_queued(self):
        jobs = [
            make_job(id="synthetic-url", url="https://example.com/jobs/1"),
            make_job(
                id="credential-url",
                url="https://private:secret@www.linkedin.com/jobs/view/9000000002",
            ),
            make_job(id="missing-company", company="No especificada"),
            make_job(id="missing-title", title="No especificado"),
        ]
        with tempfile.TemporaryDirectory() as output:
            report = self.run_jobs(jobs, output)

        self.assertEqual(report["review_queue"], [])


if __name__ == "__main__":
    unittest.main()
