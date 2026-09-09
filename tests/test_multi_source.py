import unittest
from pathlib import Path

from jobhunter_ai.models import Job
from jobhunter_ai.sources import (
    JobSource,
    JobicyApiSource,
    JsonJobSource,
    MultiJobSource,
    RssJobSource,
    load_configured_source,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def make_job(job_id: str, *, url: str = "", title: str = "Security Analyst", company: str = "Example Security") -> Job:
    return Job(
        id=job_id,
        title=title,
        company=company,
        location="Remote",
        url=url,
        description="Support security operations.",
        required_skills=[],
        preferred_skills=[],
        keywords=[],
    )


class StaticJobSource(JobSource):
    def __init__(self, jobs: list[Job]) -> None:
        self.jobs = jobs

    def fetch_jobs(self) -> list[Job]:
        return self.jobs


class MultiJobSourceTests(unittest.TestCase):
    def test_combines_json_and_rss_sources(self):
        source = MultiJobSource(
            [
                JsonJobSource("data/sample_jobs.json"),
                RssJobSource(FIXTURE_DIR / "jobs.rss"),
            ]
        )

        jobs = source.fetch_jobs()

        self.assertEqual(len(jobs), 4)
        self.assertEqual(jobs[-1].id, "rss-job-001")

    def test_removes_duplicates_by_url_and_keeps_first(self):
        first = make_job("first", url="https://example.com/jobs/1")
        duplicate = make_job("duplicate", url="https://example.com/jobs/1")

        jobs = MultiJobSource([StaticJobSource([first]), StaticJobSource([duplicate])]).fetch_jobs()

        self.assertEqual([job.id for job in jobs], ["first"])

    def test_removes_duplicates_without_url_by_normalized_title_and_company(self):
        first = make_job("first", title="  Security  Analyst ", company="Example Security")
        duplicate = make_job("duplicate", title="security analyst", company=" example   security ")

        jobs = MultiJobSource([StaticJobSource([first]), StaticJobSource([duplicate])]).fetch_jobs()

        self.assertEqual([job.id for job in jobs], ["first"])

    def test_loads_sources_from_json_configuration(self):
        source = load_configured_source("data/sources.example.json")

        self.assertIsInstance(source.sources[0], JobicyApiSource)
        self.assertEqual(len(source.sources), 3)


if __name__ == "__main__":
    unittest.main()
