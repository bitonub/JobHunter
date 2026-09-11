import base64
import json
import tempfile
import unittest
from pathlib import Path

from jobhunter_ai.cli import build_parser
from jobhunter_ai.pipeline import run_pipeline
from jobhunter_ai.sources import (
    GmailLabelJobSource,
    GmailLabelNotFoundError,
    load_configured_source,
)
from jobhunter_ai.sources.gmail_label_source import GMAIL_SCOPES


FIXTURE_DIR = Path(__file__).parent / "fixtures"
EMAIL_FIXTURE_DIR = FIXTURE_DIR / "email_alerts"


class FakeRequest:
    def __init__(self, response):
        self.response = response

    def execute(self):
        return self.response


class FakeLabelsResource:
    def __init__(self, service):
        self.service = service

    def list(self, **kwargs):
        self.service.operations.append(("labels.list", kwargs))
        return FakeRequest({"labels": self.service.labels})


class FakeMessagesResource:
    def __init__(self, service):
        self.service = service

    def list(self, **kwargs):
        self.service.operations.append(("messages.list", kwargs))
        return FakeRequest({"messages": self.service.messages})

    def get(self, **kwargs):
        self.service.operations.append(("messages.get", kwargs))
        if kwargs.get("format") == "metadata":
            return FakeRequest({
                "payload": {
                    "headers": [
                        {
                            "name": "From",
                            "value": self.service.senders[kwargs["id"]],
                        }
                    ]
                }
            })
        return FakeRequest({"raw": self.service.raw_messages[kwargs["id"]]})


class FakeUsersResource:
    def __init__(self, service):
        self.service = service

    def labels(self):
        return FakeLabelsResource(self.service)

    def messages(self):
        return FakeMessagesResource(self.service)


class FakeGmailService:
    def __init__(self, labels, messages, raw_messages, senders):
        self.labels = labels
        self.messages = messages
        self.raw_messages = raw_messages
        self.senders = senders
        self.operations = []

    def users(self):
        return FakeUsersResource(self)


def encoded_email(name: str) -> str:
    raw = (EMAIL_FIXTURE_DIR / name).read_bytes()
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


class GmailLabelJobSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api_fixture = json.loads(
            (FIXTURE_DIR / "gmail_api.json").read_text(encoding="utf-8")
        )

    def make_service(
        self,
        *,
        labels=None,
        messages=None,
        raw_messages=None,
        senders=None,
    ):
        return FakeGmailService(
            labels=self.api_fixture["labels"] if labels is None else labels,
            messages=self.api_fixture["messages"] if messages is None else messages,
            raw_messages=raw_messages or {
                "gmail-synthetic-occ": encoded_email("occ.eml"),
                "gmail-synthetic-indeed": encoded_email("indeed.eml"),
            },
            senders=senders or {
                "gmail-synthetic-occ": "Synthetic Alerts <alerts@occ.example>",
                "gmail-synthetic-indeed": "Synthetic Alerts <alerts@indeed.example>",
                "gmail-synthetic-link": "Synthetic Alerts <alerts@occ.example>",
                "gmail-synthetic-digest": "Synthetic Alerts <alerts@linkedin.example>",
            },
        )

    def test_uses_only_readonly_scope(self):
        self.assertEqual(
            GMAIL_SCOPES,
            ("https://www.googleapis.com/auth/gmail.readonly",),
        )

    def test_rejects_oauth_token_with_additional_scopes(self):
        credentials = type(
            "SyntheticCredentials",
            (),
            {
                "granted_scopes": [
                    "https://www.googleapis.com/auth/gmail.readonly",
                    "https://www.googleapis.com/auth/gmail.modify",
                ],
                "scopes": None,
            },
        )()

        with self.assertRaisesRegex(RuntimeError, "only gmail.readonly"):
            GmailLabelJobSource._validate_scopes(credentials)

    def test_reads_only_resolved_label_id_and_converts_raw_messages(self):
        service = self.make_service()
        source = GmailLabelJobSource(
            None,
            ["occ.example", "indeed.example"],
            service=service,
            max_messages=2,
        )

        jobs = source.fetch_jobs()

        self.assertEqual([job.title for job in jobs], [
            "Practicante de Ciberseguridad",
            "Junior Support Intern",
        ])
        self.assertEqual(
            service.operations[1],
            (
                "messages.list",
                {
                    "userId": "me",
                    "labelIds": ["Label_JobHunter_Alertas"],
                    "maxResults": 2,
                },
            ),
        )
        self.assertNotIn("q", service.operations[1][1])

    def test_excludes_disallowed_sender_domain_with_clear_reason(self):
        service = self.make_service(
            messages=[{"id": "gmail-synthetic-occ"}],
        )
        source = GmailLabelJobSource(
            None,
            ["indeed.example"],
            service=service,
        )

        self.assertEqual(source.fetch_jobs(), [])
        self.assertEqual(source.discarded_messages, [
            {
                "sender_domain": "occ.example",
                "reason": "Dominio de remitente no permitido: occ.example.",
            }
        ])
        self.assertFalse(any(
            operation == "messages.get" and arguments.get("format") == "raw"
            for operation, arguments in service.operations
        ))

    def test_missing_label_stops_before_reading_messages(self):
        service = self.make_service(labels=[{"id": "INBOX", "name": "INBOX"}])
        source = GmailLabelJobSource(
            None,
            ["occ.example"],
            service=service,
        )

        with self.assertRaisesRegex(GmailLabelNotFoundError, "JobHunter/Alertas"):
            source.fetch_jobs()

        self.assertEqual(service.operations, [("labels.list", {"userId": "me"})])

    def test_missing_token_fails_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            missing_token = Path(directory) / "gmail_token.json"
            source = GmailLabelJobSource(missing_token, ["occ.example"])

            with self.assertRaisesRegex(FileNotFoundError, "token file was not found"):
                source.fetch_jobs()

    def test_client_exposes_no_email_modification_operations(self):
        service = self.make_service(messages=[{"id": "gmail-synthetic-occ"}])
        source = GmailLabelJobSource(
            None,
            ["occ.example"],
            service=service,
        )

        source.fetch_jobs()

        self.assertEqual(
            [operation for operation, _ in service.operations],
            ["labels.list", "messages.list", "messages.get", "messages.get"],
        )
        self.assertEqual(service.operations[2][1]["format"], "metadata")
        self.assertEqual(service.operations[3][1]["format"], "raw")

    def test_gmail_synthetic_link_is_rejected_by_pipeline(self):
        service = self.make_service(
            messages=[{"id": "gmail-synthetic-link"}],
            raw_messages={
                "gmail-synthetic-link": encoded_email("synthetic_link.eml"),
            },
        )
        source = GmailLabelJobSource(
            None,
            ["occ.example"],
            service=service,
        )

        with tempfile.TemporaryDirectory() as output:
            report = run_pipeline(
                "data/profile.example.json",
                source,
                output,
                preferences_path="data/preferences.json",
                job_terms_path="data/job_terms.json",
            )

        self.assertEqual(report["alerts"], [])
        self.assertEqual(report["compatible_jobs"], 0)
        self.assertEqual(report["diagnostics"]["rejected_synthetic_links"], 1)
        self.assertEqual(
            [operation for operation, _ in service.operations],
            ["labels.list", "messages.list", "messages.get", "messages.get"],
        )

    def test_gmail_digest_returns_multiple_jobs_from_one_raw_message(self):
        service = self.make_service(
            messages=[{"id": "gmail-synthetic-digest"}],
            raw_messages={
                "gmail-synthetic-digest": encoded_email("linkedin_digest.eml"),
            },
        )
        source = GmailLabelJobSource(
            None,
            ["linkedin.example"],
            service=service,
            max_messages=1,
        )

        jobs = source.fetch_jobs()

        self.assertEqual(len(jobs), 2)
        self.assertEqual(
            [job.title for job in jobs],
            ["Security Intern", "Technical Support Trainee"],
        )
        self.assertTrue(all(job.url.startswith("https://www.linkedin.com/jobs/view/") for job in jobs))

    def test_cli_accepts_gmail_configuration(self):
        args = build_parser().parse_args([
            "run",
            "--profile", "data/profile.example.json",
            "--gmail-token", "data/gmail_token.json",
            "--gmail-label", "JobHunter/Alertas",
            "--gmail-allowed-domain", "occ.example",
            "--gmail-allowed-domain", "indeed.example,linkedin.example",
            "--gmail-max-messages", "25",
        ])

        self.assertEqual(args.gmail_token, "data/gmail_token.json")
        self.assertEqual(args.gmail_label, "JobHunter/Alertas")
        self.assertEqual(
            args.gmail_allowed_domain,
            ["occ.example", "indeed.example,linkedin.example"],
        )
        self.assertEqual(args.gmail_max_messages, 25)

    def test_sources_configuration_builds_gmail_source(self):
        source = load_configured_source("data/sources.gmail.example.json")
        gmail_source = source.sources[0]

        self.assertIsInstance(gmail_source, GmailLabelJobSource)
        self.assertEqual(gmail_source.label_name, "JobHunter/Alertas")
        self.assertEqual(
            gmail_source.allowed_sender_domains,
            ("occ.example", "indeed.example", "linkedin.example"),
        )
        self.assertEqual(gmail_source.max_messages, 50)


if __name__ == "__main__":
    unittest.main()
