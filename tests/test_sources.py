import unittest
from pathlib import Path

from jobhunter_ai.filters import evaluate_job
from jobhunter_ai.io import load_json
from jobhunter_ai.matcher import match_job
from jobhunter_ai.models import Job, Profile
from jobhunter_ai.sources import JobSource, JsonJobSource, RssJobSource


FIXTURE_DIR = Path(__file__).parent / "fixtures"


class InMemoryJobSource(JobSource):
    def fetch_jobs(self) -> list[Job]:
        return [
            Job(
                id="test-job",
                title="Test Job",
                company="Test Company",
                location="Remote",
                url="https://example.com/jobs/test-job",
                description="A test job.",
                required_skills=[],
                preferred_skills=[],
                keywords=[],
            )
        ]


class JobSourceTests(unittest.TestCase):
    def test_job_source_requires_an_implementation(self):
        with self.assertRaises(TypeError):
            JobSource()

    def test_job_source_returns_job_objects(self):
        jobs = InMemoryJobSource().fetch_jobs()
        self.assertTrue(jobs)
        self.assertTrue(all(isinstance(job, Job) for job in jobs))


class JsonJobSourceTests(unittest.TestCase):
    def test_loads_sample_jobs_as_job_objects(self):
        jobs = JsonJobSource("data/sample_jobs.json").fetch_jobs()

        self.assertEqual(len(jobs), 3)
        self.assertTrue(all(isinstance(job, Job) for job in jobs))
        self.assertEqual(jobs[0].id, "analista-ciberseguridad-jr-001")


class RssJobSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preferences = load_json("data/preferences.json")
        cls.profile = Profile.from_dict(load_json("data/profile.example.json"))

    def test_loads_valid_rss_feed(self):
        jobs = RssJobSource(FIXTURE_DIR / "jobs.rss").fetch_jobs()

        self.assertEqual(len(jobs), 1)
        self.assertIsInstance(jobs[0], Job)
        self.assertEqual(jobs[0].id, "rss-job-001")
        self.assertEqual(jobs[0].title, "Security Intern")
        self.assertEqual(jobs[0].company, "Example Security")
        self.assertEqual(jobs[0].location, "Monterrey")
        self.assertEqual(jobs[0].url, "https://example.com/jobs/rss-job-001")
        self.assertEqual(jobs[0].description, "Support security monitoring and reporting.")
        self.assertEqual(jobs[0].source, "rss")
        self.assertEqual(jobs[0].employment_type, "internship")
        self.assertEqual(jobs[0].schedule, "unknown")

    def test_rss_job_without_requirements_is_not_compatible(self):
        job = RssJobSource(FIXTURE_DIR / "jobs.rss").fetch_jobs()[0]

        result = match_job(self.profile, job)

        self.assertEqual(result.score, 0.0)
        self.assertFalse(result.compatible)

    def test_infers_internship_from_security_intern(self):
        job = RssJobSource(FIXTURE_DIR / "jobs.rss").fetch_jobs()[0]

        self.assertEqual(job.employment_type, "internship")

    def test_infers_part_time_from_medium_tiempo(self):
        job = RssJobSource(FIXTURE_DIR / "part_time.rss").fetch_jobs()[0]

        self.assertEqual(job.employment_type, "part-time")
        self.assertEqual(job.schedule, "part-time")

    def test_supports_atom_feed(self):
        jobs = RssJobSource(FIXTURE_DIR / "jobs.atom").fetch_jobs()

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].id, "tag:example.com,2026:atom-job-001")
        self.assertEqual(jobs[0].company, "Example Atom Company")
        self.assertEqual(jobs[0].url, "https://example.com/jobs/atom-job-001")

    def test_handles_incomplete_entry(self):
        jobs = RssJobSource(FIXTURE_DIR / "incomplete.rss").fetch_jobs()

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].id, "rss-entry-1")
        self.assertEqual(jobs[0].title, "Incomplete listing")
        self.assertEqual(jobs[0].company, "No especificada")
        self.assertEqual(jobs[0].location, "No especificada")
        self.assertEqual(jobs[0].url, "")
        self.assertEqual(jobs[0].description, "")

    def test_unknown_employment_type_is_rejected_by_filters(self):
        job = RssJobSource(FIXTURE_DIR / "incomplete.rss").fetch_jobs()[0]

        result = evaluate_job(job, self.preferences)

        self.assertFalse(result.accepted)
        self.assertEqual(result.employment_type, "unknown")
        self.assertTrue(any("Tipo de empleo no compatible" in reason for reason in result.reasons))

    def test_returns_no_jobs_for_empty_feed(self):
        self.assertEqual(RssJobSource(FIXTURE_DIR / "empty.rss").fetch_jobs(), [])


if __name__ == "__main__":
    unittest.main()
