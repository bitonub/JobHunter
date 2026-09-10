import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from jobhunter_ai.cli import build_parser
from jobhunter_ai.models import Job
from jobhunter_ai.pipeline import run_pipeline
from jobhunter_ai.sources import JobSource
from jobhunter_ai.storage import (
    JobStateStatus,
    SQLiteJobStateStore,
    build_job_state_key,
)


class StaticJobSource(JobSource):
    def __init__(self, jobs: list[Job]) -> None:
        self.jobs = jobs

    def fetch_jobs(self) -> list[Job]:
        return self.jobs


def make_job(**overrides) -> Job:
    values = {
        "id": "synthetic-job-001",
        "title": "Security Intern",
        "company": "Synthetic Security",
        "location": "Remote",
        "url": "https://jobs.example.test/jobs/security-intern-001",
        "description": "PRIVATE_EMAIL_BODY_SENTINEL",
        "required_skills": ["Python"],
        "preferred_skills": ["Linux"],
        "keywords": ["SQL"],
        "source": "synthetic-source",
        "employment_type": "internship",
        "schedule": "part-time",
        "experience_level": "student",
    }
    values.update(overrides)
    return Job(**values)


def run_with_store(source, output: Path, store: SQLiteJobStateStore):
    return run_pipeline(
        "data/profile.example.json",
        source,
        str(output),
        preferences_path="data/preferences.json",
        job_terms_path="data/job_terms.json",
        state_store=store,
    )


class SQLiteJobStateStoreTests(unittest.TestCase):
    def test_pipeline_keeps_compatible_status_without_alert_confirmation(self):
        job = make_job()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = SQLiteJobStateStore(root / "jobhunter.db")
            try:
                report = run_with_store(StaticJobSource([job]), root / "output", store)
                state = store.get(job)
                with self.assertRaisesRegex(ValueError, "mark_alerted"):
                    store.record(job, JobStateStatus.ALERTED, 100.0)
            finally:
                store.close()

        self.assertEqual(report["new_jobs"], 1)
        self.assertEqual(report["compatible_jobs"], 1)
        self.assertIsNotNone(state)
        self.assertEqual(state.status, JobStateStatus.COMPATIBLE.value)
        self.assertEqual(state.score, 100.0)

    def test_manually_alerted_job_is_skipped_on_next_run(self):
        job = make_job()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            store = SQLiteJobStateStore(root / "jobhunter.db")
            try:
                first = run_with_store(StaticJobSource([job]), output, store)
                store.mark_alerted(job, first["alerts"][0]["analysis"]["score"])
                cv_path = Path(first["alerts"][0]["tailored_cv_path"])
                cv_path.write_text("DO_NOT_OVERWRITE", encoding="utf-8")

                second = run_with_store(StaticJobSource([job]), output, store)
                state = store.get(job)
            finally:
                store.close()

            self.assertEqual(second["new_jobs"], 0)
            self.assertEqual(second["previously_seen_jobs"], 1)
            self.assertEqual(second["skipped_alerted_jobs"], 1)
            self.assertEqual(second["alerts"], [])
            self.assertEqual(cv_path.read_text(encoding="utf-8"), "DO_NOT_OVERWRITE")
            self.assertIsNotNone(state)
            self.assertEqual(state.status, JobStateStatus.ALERTED.value)
            self.assertEqual(state.score, 100.0)

    def test_failed_alert_before_confirmation_remains_available_for_retry(self):
        job = make_job()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            store = SQLiteJobStateStore(root / "jobhunter.db")
            try:
                first = run_with_store(StaticJobSource([job]), output, store)
                cv_path = Path(first["alerts"][0]["tailored_cv_path"])
                cv_path.write_text("RETRY_MUST_REPLACE_THIS", encoding="utf-8")

                second = run_with_store(StaticJobSource([job]), output, store)
                state = store.get(job)
            finally:
                store.close()

            self.assertEqual(second["new_jobs"], 0)
            self.assertEqual(second["previously_seen_jobs"], 1)
            self.assertEqual(second["skipped_alerted_jobs"], 0)
            self.assertEqual(second["compatible_jobs"], 1)
            self.assertEqual(len(second["alerts"]), 1)
            self.assertNotEqual(
                cv_path.read_text(encoding="utf-8"),
                "RETRY_MUST_REPLACE_THIS",
            )
            self.assertEqual(state.status, JobStateStatus.COMPATIBLE.value)

    def test_different_source_link_or_identifier_is_new(self):
        original = make_job()
        variants = [
            replace(original, source="another-source"),
            replace(original, url="https://jobs.example.test/jobs/security-intern-002"),
            replace(original, id="synthetic-job-002"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = SQLiteJobStateStore(root / "jobhunter.db")
            try:
                run_with_store(StaticJobSource([original]), root / "first", store)
                reports = [
                    run_with_store(StaticJobSource([job]), root / f"variant-{index}", store)
                    for index, job in enumerate(variants)
                ]
            finally:
                store.close()

        self.assertEqual([report["new_jobs"] for report in reports], [1, 1, 1])
        self.assertEqual([report["previously_seen_jobs"] for report in reports], [0, 0, 0])

    def test_tracking_only_link_changes_keep_same_identity(self):
        first = make_job(url="https://jobs.example.test/jobs/1?utm_source=mail&id=7")
        second = replace(
            first,
            url="https://jobs.example.test/jobs/1?id=7&utm_campaign=weekly#details",
        )

        self.assertEqual(build_job_state_key(first), build_job_state_key(second))

    def test_database_contains_only_minimal_hashed_state(self):
        job = make_job()
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "jobhunter.db"
            store = SQLiteJobStateStore(database)
            try:
                run_with_store(StaticJobSource([job]), Path(directory) / "output", store)
            finally:
                store.close()

            connection = sqlite3.connect(database)
            try:
                columns = [
                    row[1]
                    for row in connection.execute("PRAGMA table_info(job_state)").fetchall()
                ]
                row = connection.execute(
                    "SELECT identifier_hash, source, link_hash, first_seen, last_seen, status, score "
                    "FROM job_state"
                ).fetchone()
            finally:
                connection.close()
            database_bytes = database.read_bytes()

        self.assertEqual(columns, [
            "identifier_hash",
            "source",
            "link_hash",
            "first_seen",
            "last_seen",
            "status",
            "score",
        ])
        self.assertEqual(len(row[0]), 64)
        self.assertEqual(len(row[2]), 64)
        self.assertEqual(row[1], "synthetic-source")
        self.assertEqual(row[5], "compatible")
        self.assertNotIn(job.id.encode(), database_bytes)
        self.assertNotIn(job.url.encode(), database_bytes)
        self.assertNotIn(job.description.encode(), database_bytes)
        self.assertNotIn(b"Candidate Example", database_bytes)
        self.assertNotIn(b"candidate@example.com", database_bytes)

    def test_pipeline_records_filter_match_and_cv_states(self):
        compatible = make_job(id="compatible")
        discarded = make_job(
            id="discarded",
            title="Full-time Security Engineer",
            employment_type="full-time",
        )
        reviewable = make_job(
            id="reviewable",
            required_skills=["Synthetic Unmatched Requirement"],
            preferred_skills=["Another Unmatched Requirement"],
            keywords=["Unmatched Keyword"],
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = SQLiteJobStateStore(root / "jobhunter.db")
            try:
                report = run_with_store(
                    StaticJobSource([compatible, discarded, reviewable]),
                    root / "output",
                    store,
                )
                states = {
                    job.id: store.get(job).status
                    for job in (compatible, discarded, reviewable)
                }
            finally:
                store.close()

            generated_cvs = list((root / "output").glob("cv_adaptado_*.md"))

        self.assertEqual(report["new_jobs"], 3)
        self.assertEqual(report["filtered_out_jobs"], 1)
        self.assertEqual(report["compatible_jobs"], 1)
        self.assertEqual(states, {
            "compatible": "compatible",
            "discarded": "descartado",
            "reviewable": "revisable",
        })
        self.assertEqual(len(generated_cvs), 1)
        self.assertTrue(generated_cvs[0].name.endswith("compatible.md"))

    def test_cli_accepts_optional_state_database(self):
        args = build_parser().parse_args([
            "run",
            "--profile", "data/profile.example.json",
            "--jobs", "data/sample_jobs.json",
            "--state-db", "data/jobhunter.db",
        ])

        self.assertEqual(args.state_db, "data/jobhunter.db")


if __name__ == "__main__":
    unittest.main()
