import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from jobhunter_ai.cli import build_parser
from jobhunter_ai.job_quality import evaluate_email_job_quality
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
        self.assertEqual(len(self.jobs), 7)

    def test_extracts_multiple_jobs_from_synthetic_digest(self):
        jobs = EmailAlertJobSource(FIXTURE_DIR / "linkedin_digest.eml").fetch_jobs()

        self.assertEqual(len(jobs), 2)
        self.assertEqual(
            [job.title for job in jobs],
            ["Security Intern", "Technical Support Trainee"],
        )
        self.assertEqual(
            [job.company for job in jobs],
            ["Northstar Security Lab", "Contoso Support Lab"],
        )
        self.assertEqual(
            [job.location for job in jobs],
            ["Monterrey, Nuevo León", "Remote"],
        )
        self.assertEqual(
            [job.url for job in jobs],
            [
                "https://www.linkedin.com/jobs/view/2000000001",
                "https://www.linkedin.com/jobs/view/2000000002",
            ],
        )
        self.assertEqual(
            [job.employment_type for job in jobs],
            ["internship", "part-time"],
        )
        self.assertTrue(all(job.description for job in jobs))
        self.assertEqual(len({job.id for job in jobs}), 2)

    def test_extracts_plain_text_occ_alert(self):
        job = self.jobs["occ-alert-001@occ.example"]

        self.assertEqual(job.sender, "alerts@occ.example")
        self.assertEqual(job.subject, "Alerta de empleo: Practicante de Ciberseguridad")
        self.assertEqual(job.title, "Practicante de Ciberseguridad")
        self.assertEqual(job.company, "Laboratorio Digital Ejemplo")
        self.assertEqual(job.location, "Monterrey, Nuevo León")
        self.assertEqual(
            job.url,
            "https://www.occ.com.mx/empleo/oferta/10000001-practicante-ciberseguridad",
        )
        self.assertEqual(job.links, [job.url])
        self.assertEqual(job.source, "occ.example")
        self.assertEqual(job.employment_type, "internship")

    def test_extracts_basic_html_and_preserves_links(self):
        job = self.jobs["indeed-alert-001@indeed.example"]

        self.assertEqual(job.title, "Junior Support Intern")
        self.assertEqual(job.company, "Northstar Systems")
        self.assertEqual(job.location, "Remote")
        self.assertNotIn("<html>", job.description)
        self.assertEqual(job.url, "https://mx.indeed.com/viewjob?jk=0000000000000001")
        self.assertEqual(
            job.links,
            [
                "https://mx.indeed.com/viewjob?jk=0000000000000001",
                "https://profile.indeed.com/preferences",
            ],
        )
        self.assertEqual(job.source, "indeed.example")
        self.assertEqual(job.employment_type, "internship")

    def test_multipart_linkedin_alert_keeps_html_application_link(self):
        job = self.jobs["linkedin-alert-001@linkedin.example"]

        self.assertEqual(job.title, "Network Trainee")
        self.assertEqual(job.company, "Example Infrastructure")
        self.assertEqual(job.location, "San Nicolás de los Garza, Nuevo León")
        self.assertIn("supporting TCP/IP networks", job.description)
        self.assertEqual(job.url, "https://www.linkedin.com/jobs/view/1000000001")
        self.assertIn(job.url, job.links)
        self.assertIn(
            "https://www.linkedin.com/company/northstar-systems-lab",
            job.links,
        )
        self.assertEqual(job.source, "linkedin.example")
        self.assertEqual(job.employment_type, "trainee")

    def test_rejects_synthetic_application_url(self):
        job = self.jobs["synthetic-link-alert-001@occ.example"]

        self.assertEqual(job.url, "")
        self.assertEqual(job.links, ["https://example.com/jobs/security-intern"])

    def test_required_email_fields_are_validated_before_matching(self):
        complete = self.jobs["occ-alert-001@occ.example"]
        cases = [
            (replace(complete, title="No especificado"), "título"),
            (replace(complete, company="No especificada"), "empresa"),
            (replace(complete, url=""), "URL de postulación real"),
            (replace(complete, description="Apply now"), "descripción"),
        ]

        for job, missing_field in cases:
            with self.subTest(missing_field=missing_field):
                quality = evaluate_email_job_quality(job)
                self.assertFalse(quality.accepted)
                self.assertIn(missing_field, quality.missing_fields)

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

    def test_pipeline_processes_each_synthetic_digest_card(self):
        source = EmailAlertJobSource(FIXTURE_DIR / "linkedin_digest.eml")
        with tempfile.TemporaryDirectory() as output:
            report = run_pipeline(
                "data/profile.example.json",
                source,
                output,
                preferences_path="data/preferences.json",
                job_terms_path="data/job_terms.json",
            )

        self.assertEqual(report["total_jobs"], 2)
        self.assertEqual(report["eligible_jobs"], 2)
        self.assertEqual(report["compatible_jobs"], 2)
        self.assertEqual(
            [alert["job"]["title"] for alert in report["alerts"]],
            ["Security Intern", "Technical Support Trainee"],
        )

    def test_pipeline_rejects_synthetic_link_before_matching_or_cv(self):
        source = EmailAlertJobSource(FIXTURE_DIR / "synthetic_link.eml")
        with (
            tempfile.TemporaryDirectory() as output,
            patch("jobhunter_ai.pipeline.match_job") as matcher,
            patch("jobhunter_ai.pipeline.build_tailored_cv") as tailor,
        ):
            report = run_pipeline(
                "data/profile.example.json",
                source,
                output,
                preferences_path="data/preferences.json",
                job_terms_path="data/job_terms.json",
            )
            generated_cvs = list(Path(output).glob("cv_adaptado_*.md"))

        matcher.assert_not_called()
        tailor.assert_not_called()
        self.assertEqual(report["eligible_jobs"], 0)
        self.assertEqual(report["compatible_jobs"], 0)
        self.assertEqual(report["alerts"], [])
        self.assertEqual(generated_cvs, [])
        self.assertEqual(report["diagnostics"]["rejected_synthetic_links"], 1)
        self.assertEqual(report["diagnostics"]["insufficient_data_jobs"], 1)
        quality = report["filtered_out"][0]["quality"]
        self.assertIn("URL de postulación real", quality["missing_fields"])
        self.assertTrue(any("Enlaces sintéticos rechazados" in reason for reason in quality["reasons"]))

    def test_pipeline_rejects_incomplete_email_with_clear_reason(self):
        source = EmailAlertJobSource(FIXTURE_DIR / "unknown.eml")
        with tempfile.TemporaryDirectory() as output:
            report = run_pipeline(
                "data/profile.example.json",
                source,
                output,
                preferences_path="data/preferences.json",
                job_terms_path="data/job_terms.json",
            )
            generated_cvs = list(Path(output).glob("cv_adaptado_*.md"))

        self.assertEqual(report["alerts"], [])
        self.assertEqual(report["compatible_jobs"], 0)
        self.assertEqual(generated_cvs, [])
        self.assertEqual(report["diagnostics"]["insufficient_data_jobs"], 1)
        example = report["diagnostics"]["insufficient_data_examples"][0]
        self.assertIn("Datos insuficientes", " ".join(example["reasons"]))
        self.assertEqual(
            report["filtered_out"][0]["quality"]["missing_fields"],
            ["título", "empresa", "URL de postulación real"],
        )


if __name__ == "__main__":
    unittest.main()
