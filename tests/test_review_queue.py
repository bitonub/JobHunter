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
        "location": "Toronto, Canada",
        "url": "https://www.linkedin.com/jobs/view/9000000001",
        "description": "Remote role monitoring Python automation and Linux infrastructure.",
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
    def run_jobs(
        self,
        jobs: list[Job],
        output: str,
        preferences: str = "data/search_preferences.example.json",
    ) -> dict:
        return run_pipeline(
            "data/profile.example.json",
            StaticJobSource(jobs),
            output,
            preferences_path=preferences,
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
        self.assertEqual(report["review_queue"][0]["location"], "Toronto, Canada")

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

    def test_remote_job_without_location_is_rejected_from_queue(self):
        with tempfile.TemporaryDirectory() as output:
            report = self.run_jobs(
                [make_job(location="No especificada")],
                output,
            )

        self.assertEqual(report["review_queue"], [])
        self.assertEqual(
            report["review_queue_diagnostics"][
                "insufficient_work_mode_or_location"
            ]["count"],
            1,
        )

    def test_unknown_work_mode_is_rejected_from_queue(self):
        job = make_job(
            location="Monterrey, Nuevo León",
            description="Monitor Python automation and Linux infrastructure.",
        )
        with tempfile.TemporaryDirectory() as output:
            report = self.run_jobs([job], output)

        self.assertEqual(report["review_queue"], [])
        diagnostic = report["review_queue_diagnostics"][
            "insufficient_work_mode_or_location"
        ]
        self.assertEqual(diagnostic["count"], 1)
        self.assertIn("modalidad o ubicación", diagnostic["reason"])

    def test_hybrid_job_requires_metropolitan_nuevo_leon_location(self):
        inside = make_job(
            id="inside-location",
            location="San Pedro Garza García, Nuevo León",
            description="Hybrid role monitoring Python and Linux infrastructure.",
        )
        outside = make_job(
            id="outside-location",
            location="Linares, Nuevo León",
            description="Hybrid role monitoring Python and Linux infrastructure.",
        )
        with tempfile.TemporaryDirectory() as output:
            report = self.run_jobs([inside, outside], output)

        self.assertEqual(
            [entry["title"] for entry in report["review_queue"]],
            [inside.title],
        )
        diagnostic = report["review_queue_diagnostics"]["outside_allowed_location"]
        self.assertEqual(diagnostic["count"], 1)
        self.assertIn("Nuevo León", diagnostic["reason"])

    def test_basic_preferences_still_apply_safe_review_location_rules(self):
        remote = make_job(id="remote-with-basic-preferences")
        outside = make_job(
            id="outside-with-basic-preferences",
            location="Linares, Nuevo León",
            description="Hybrid role monitoring Python and Linux infrastructure.",
        )
        with tempfile.TemporaryDirectory() as output:
            report = self.run_jobs(
                [remote, outside],
                output,
                preferences="data/preferences.json",
            )

        self.assertFalse(report["preferences"]["allow_unknown_employment_type"])
        self.assertEqual(len(report["review_queue"]), 1)
        self.assertEqual(report["review_queue"][0]["location"], "Toronto, Canada")
        self.assertEqual(
            report["review_queue_diagnostics"]["outside_allowed_location"]["count"],
            1,
        )

    def test_full_time_signal_is_rejected_even_when_title_says_junior(self):
        job = make_job(
            title="Junior Cloud Operations Analyst",
            description="Remote full-time role using Python and Linux.",
        )
        with tempfile.TemporaryDirectory() as output:
            report = self.run_jobs([job], output)

        self.assertEqual(report["review_queue"], [])
        diagnostic = report["review_queue_diagnostics"]["full_time_detected"]
        self.assertEqual(diagnostic["count"], 1)
        self.assertIn("tiempo completo", diagnostic["reason"])

    def test_spanish_full_time_signals_are_rejected(self):
        jobs = [
            make_job(
                id="tiempo-completo",
                description="Puesto remoto de tiempo completo con Python.",
            ),
            make_job(
                id="jornada-completa",
                description="Puesto remoto de jornada completa con Linux.",
            ),
        ]
        with tempfile.TemporaryDirectory() as output:
            report = self.run_jobs(jobs, output)

        self.assertEqual(report["review_queue"], [])
        self.assertEqual(
            report["review_queue_diagnostics"]["full_time_detected"]["count"],
            2,
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
