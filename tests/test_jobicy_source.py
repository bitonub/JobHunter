import unittest
from pathlib import Path

from jobhunter_ai.filters import evaluate_job
from jobhunter_ai.io import load_json
from jobhunter_ai.sources import JobicyApiSource


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "jobicy.json"


class JobicyApiSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preferences = load_json("data/preferences.json")

    def test_maps_internship_part_time_and_full_time_jobs(self):
        jobs = JobicyApiSource(str(FIXTURE_PATH)).fetch_jobs()

        self.assertEqual(len(jobs), 3)
        self.assertEqual(jobs[0].id, "1001")
        self.assertEqual(jobs[0].employment_type, "internship")
        self.assertEqual(jobs[1].id, "python-developer-part-time")
        self.assertEqual(jobs[1].employment_type, "part-time")
        self.assertEqual(jobs[2].employment_type, "full-time")

    def test_preserves_jobicy_fields_and_source_url(self):
        job = JobicyApiSource(str(FIXTURE_PATH)).fetch_jobs()[0]

        self.assertEqual(job.title, "Security Intern")
        self.assertEqual(job.company, "Example Security")
        self.assertEqual(job.location, "Worldwide")
        self.assertEqual(job.description, "Support security operations.")
        self.assertEqual(job.experience_level, "Entry-level")
        self.assertEqual(job.source, "jobicy")
        self.assertEqual(job.url, "https://example.com/jobs/security-intern-1001")

    def test_existing_filters_decide_employment_type(self):
        jobs = JobicyApiSource(str(FIXTURE_PATH)).fetch_jobs()

        self.assertTrue(evaluate_job(jobs[0], self.preferences).accepted)
        self.assertTrue(evaluate_job(jobs[1], self.preferences).accepted)
        self.assertFalse(evaluate_job(jobs[2], self.preferences).accepted)


if __name__ == "__main__":
    unittest.main()
