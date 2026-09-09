import unittest

from jobhunter_ai.models import Job
from jobhunter_ai.sources import JobSource, JsonJobSource


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


if __name__ == "__main__":
    unittest.main()
