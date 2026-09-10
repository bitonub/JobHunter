import tempfile
import unittest
from pathlib import Path

from jobhunter_ai.cli import build_parser
from jobhunter_ai.pipeline import run_pipeline
from jobhunter_ai.sources import EmailAlertJobSource, load_configured_source


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "email_alerts"


class EmailAlertJobSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.jobs = {
            job.id: job for job in EmailAlertJobSource(FIXTURE_DIR).fetch_jobs()
        }

    def test_reads_all_eml_files_from_folder(self):
        self.assertEqual(len(self.jobs), 4)

    def test_extracts_plain_text_occ_alert(self):
        job = self.jobs["occ-alert-001@occ.example"]

        self.assertEqual(job.sender, "alerts@occ.example")
        self.assertEqual(job.subject, "Alerta de empleo: Practicante de Ciberseguridad")
        self.assertEqual(job.title, "Practicante de Ciberseguridad")
        self.assertEqual(job.company, "Laboratorio Digital Ejemplo")
        self.assertEqual(job.location, "Monterrey, Nuevo León")
        self.assertEqual(job.url, "https://jobs.occ.example/vacantes/security-intern-001")
        self.assertEqual(job.links, [job.url])
        self.assertEqual(job.source, "occ.example")

    def test_extracts_basic_html_and_preserves_links(self):
        job = self.jobs["indeed-alert-001@indeed.example"]

        self.assertEqual(job.title, "Junior Support Intern")
        self.assertEqual(job.company, "Northstar Systems")
        self.assertEqual(job.location, "Remote")
        self.assertNotIn("<html>", job.description)
        self.assertEqual(job.url, "https://jobs.indeed.example/viewjob?id=synthetic-001")
        self.assertEqual(
            job.links,
            [
                "https://jobs.indeed.example/viewjob?id=synthetic-001",
                "https://account.indeed.example/preferences",
            ],
        )
        self.assertEqual(job.source, "indeed.example")

    def test_multipart_linkedin_alert_keeps_html_application_link(self):
        job = self.jobs["linkedin-alert-001@linkedin.example"]

        self.assertEqual(job.title, "Network Trainee")
        self.assertEqual(job.company, "Example Infrastructure")
        self.assertEqual(job.location, "San Nicolás de los Garza, Nuevo León")
        self.assertIn("supporting TCP/IP networks", job.description)
        self.assertEqual(job.url, "https://jobs.linkedin.example/jobs/view/synthetic-001")
        self.assertIn(job.url, job.links)
        self.assertIn(
            "https://jobs.linkedin.example/company/example-infrastructure",
            job.links,
        )
        self.assertEqual(job.source, "linkedin.example")

    def test_incomplete_email_stays_partial_with_unknown_source(self):
        job = self.jobs["unknown-alert-001@example.test"]

        self.assertEqual(job.sender, "")
        self.assertEqual(job.title, "No especificado")
        self.assertEqual(job.company, "No especificada")
        self.assertEqual(job.location, "No especificada")
        self.assertEqual(job.url, "")
        self.assertEqual(job.links, [])
        self.assertEqual(job.source, "unknown")
        self.assertEqual(job.employment_type, "unknown")
        self.assertEqual(job.required_skills, [])
        self.assertEqual(job.preferred_skills, [])
        self.assertEqual(job.keywords, [])

    def test_explicit_provider_overrides_sender_domain(self):
        source = EmailAlertJobSource(FIXTURE_DIR / "occ.eml", provider="configured-occ")

        self.assertEqual(source.fetch_jobs()[0].source, "configured-occ")

    def test_cli_accepts_email_alert_path(self):
        args = build_parser().parse_args([
            "run",
            "--profile", "data/profile.example.json",
            "--email-alerts", str(FIXTURE_DIR),
        ])

        self.assertEqual(args.email_alerts, str(FIXTURE_DIR))

    def test_sources_configuration_supports_email_alerts(self):
        source = load_configured_source("tests/fixtures/email_sources.json")

        self.assertEqual(len(source.sources), 1)
        self.assertIsInstance(source.sources[0], EmailAlertJobSource)
        self.assertEqual(source.fetch_jobs()[0].source, "configured-occ")

    def test_pipeline_accepts_email_source_without_filter_or_match_changes(self):
        source = EmailAlertJobSource(FIXTURE_DIR / "occ.eml")
        with tempfile.TemporaryDirectory() as output:
            report = run_pipeline(
                "data/profile.example.json",
                source,
                output,
                preferences_path="data/preferences.json",
                job_terms_path="data/job_terms.json",
            )

        self.assertEqual(report["total_jobs"], 1)
        self.assertEqual(report["eligible_jobs"], 1)
        self.assertEqual(report["alerts"][0]["job"]["source"], "occ.example")
        self.assertEqual(report["alerts"][0]["job"]["sender"], "alerts@occ.example")
        self.assertIn("Python", report["alerts"][0]["job"]["required_skills"])


if __name__ == "__main__":
    unittest.main()
