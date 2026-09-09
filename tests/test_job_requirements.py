import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jobhunter_ai.io import load_json
from jobhunter_ai.job_requirements import extract_job_requirements
from jobhunter_ai.models import Job
from jobhunter_ai.pipeline import run_pipeline
from jobhunter_ai.sources import RssJobSource


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def make_job(description: str) -> Job:
    return Job(
        id="requirements-test",
        title="Security Analyst",
        company="Example Security",
        location="Remote",
        url="https://example.com/jobs/requirements-test",
        description=description,
        required_skills=[],
        preferred_skills=[],
        keywords=[],
    )


class JobRequirementsTests(unittest.TestCase):
    def test_classifies_english_required_and_preferred_terms(self):
        job = make_job("Required: Python and TCP/IP. Nice to have: Microsoft Azure. React is used by the team.")

        normalized = extract_job_requirements(job)

        self.assertEqual(normalized.required_skills, ["Python", "TCP/IP"])
        self.assertEqual(normalized.preferred_skills, ["Microsoft Azure"])
        self.assertEqual(normalized.keywords, ["React"])

    def test_classifies_spanish_required_and_preferred_terms(self):
        job = make_job(
            "Requisitos: Linux y redes. Deseable: análisis de vulnerabilidades. "
            "También se utiliza Docker."
        )

        normalized = extract_job_requirements(job)

        self.assertEqual(normalized.required_skills, ["Linux", "redes"])
        self.assertEqual(normalized.preferred_skills, ["análisis de vulnerabilidades"])
        self.assertEqual(normalized.keywords, ["Docker"])

    def test_rss_python_required_sql_preferred(self):
        rss_job = RssJobSource(FIXTURE_DIR / "requirements.rss").fetch_jobs()[0]

        normalized = extract_job_requirements(rss_job)

        self.assertEqual(normalized.required_skills, ["Python"])
        self.assertEqual(normalized.preferred_skills, ["SQL"])
        self.assertEqual(normalized.keywords, [])

    def test_pipeline_normalizes_rss_jobs_before_matching(self):
        source = RssJobSource(FIXTURE_DIR / "requirements.rss")

        with TemporaryDirectory() as output_dir:
            report = run_pipeline(
                "data/profile.example.json",
                source,
                output_dir,
                preferences_path="data/preferences.json",
            )

        normalized_job = report["alerts"][0]["job"]
        self.assertEqual(normalized_job["required_skills"], ["Python"])
        self.assertEqual(normalized_job["preferred_skills"], ["SQL"])

    def test_custom_catalog_is_supported(self):
        job = make_job("Required: Terraform. Also Kubernetes experience.")

        with TemporaryDirectory() as directory:
            terms_path = Path(directory) / "terms.json"
            terms_path.write_text('{"terms": ["Terraform", "Kubernetes"]}', encoding="utf-8")

            normalized = extract_job_requirements(job, terms_path)

        self.assertEqual(normalized.required_skills, ["Terraform"])
        self.assertEqual(normalized.keywords, ["Kubernetes"])


class JsonCompatibilityTests(unittest.TestCase):
    def test_json_job_fields_are_preserved(self):
        job = Job.from_dict(load_json("data/sample_jobs.json")[0])

        normalized = extract_job_requirements(job)

        self.assertEqual(normalized.required_skills, job.required_skills)
        self.assertEqual(normalized.preferred_skills, job.preferred_skills)
        self.assertTrue(all(keyword in normalized.keywords for keyword in job.keywords))
        self.assertIn("análisis de vulnerabilidades", normalized.keywords)


if __name__ == "__main__":
    unittest.main()
