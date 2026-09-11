import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from jobhunter_ai.cli import build_parser, main
from jobhunter_ai.gmail_oauth import GmailAuthorizationError, authorize_gmail
from jobhunter_ai.sources.gmail_label_source import GMAIL_SCOPES


SYNTHETIC_TOKEN = '{"token": "synthetic-test-token", "refresh_token": "synthetic-refresh"}'
SYNTHETIC_DESKTOP_CLIENT = '{"installed": {"client_id": "synthetic-client"}}'


class FakeCredentials:
    granted_scopes = list(GMAIL_SCOPES)
    scopes = None

    def to_json(self):
        return SYNTHETIC_TOKEN


class FakeFlow:
    def __init__(self):
        self.run_arguments = None

    def run_local_server(self, **kwargs):
        self.run_arguments = kwargs
        return FakeCredentials()


class FakeFlowClass:
    calls = []
    flow = None

    @classmethod
    def reset(cls):
        cls.calls = []
        cls.flow = FakeFlow()

    @classmethod
    def from_client_secrets_file(cls, path, scopes):
        cls.calls.append((path, scopes))
        return cls.flow


class GmailOAuthTests(unittest.TestCase):
    def setUp(self):
        FakeFlowClass.reset()

    def test_cli_accepts_local_authorization_paths(self):
        args = build_parser().parse_args([
            "authorize-gmail",
            "--client-secrets", "data/google_client_secret.json",
            "--token", "data/gmail_token.json",
        ])

        self.assertEqual(args.command, "authorize-gmail")
        self.assertEqual(args.client_secrets, "data/google_client_secret.json")
        self.assertEqual(args.token, "data/gmail_token.json")

    def test_authorization_uses_browser_and_only_readonly_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client_secrets = root / "google_client_secret.json"
            client_secrets.write_text(SYNTHETIC_DESKTOP_CLIENT, encoding="utf-8")
            token = root / "gmail_token.json"
            output = io.StringIO()

            with redirect_stdout(output):
                result = authorize_gmail(
                    client_secrets,
                    token,
                    flow_class=FakeFlowClass,
                )

            self.assertEqual(result, token)
            self.assertEqual(token.read_text(encoding="utf-8"), SYNTHETIC_TOKEN)

        self.assertEqual(FakeFlowClass.calls, [
            (str(client_secrets), list(GMAIL_SCOPES)),
        ])
        self.assertEqual(FakeFlowClass.flow.run_arguments["port"], 0)
        self.assertTrue(FakeFlowClass.flow.run_arguments["open_browser"])
        self.assertNotIn("{url}", FakeFlowClass.flow.run_arguments["authorization_prompt_message"])
        self.assertEqual(output.getvalue(), "")

    def test_missing_client_secrets_stops_before_oauth(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(FileNotFoundError, "was not found"):
                authorize_gmail(
                    root / "missing.json",
                    root / "gmail_token.json",
                    flow_class=FakeFlowClass,
                )

        self.assertEqual(FakeFlowClass.calls, [])

    def test_oauth_failure_does_not_create_or_expose_token(self):
        class FailingFlow(FakeFlow):
            def run_local_server(self, **kwargs):
                raise RuntimeError("SENSITIVE_PROVIDER_DETAIL")

        FakeFlowClass.flow = FailingFlow()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client_secrets = root / "google_client_secret.json"
            client_secrets.write_text(SYNTHETIC_DESKTOP_CLIENT, encoding="utf-8")
            token = root / "gmail_token.json"

            with self.assertRaises(GmailAuthorizationError) as context:
                authorize_gmail(
                    client_secrets,
                    token,
                    flow_class=FakeFlowClass,
                )

            self.assertFalse(token.exists())
            self.assertNotIn("SENSITIVE_PROVIDER_DETAIL", str(context.exception))

    def test_rejects_non_desktop_client_before_oauth(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client_secrets = root / "google_client_secret.json"
            client_secrets.write_text(
                '{"web": {"client_id": "synthetic-web-client"}}',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(GmailAuthorizationError, "Desktop app"):
                authorize_gmail(
                    client_secrets,
                    root / "gmail_token.json",
                    flow_class=FakeFlowClass,
                )

        self.assertEqual(FakeFlowClass.calls, [])

    def test_token_write_failure_has_clear_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client_secrets = root / "google_client_secret.json"
            client_secrets.write_text(SYNTHETIC_DESKTOP_CLIENT, encoding="utf-8")
            token = root / "gmail_token.json"

            with (
                patch(
                    "jobhunter_ai.gmail_oauth.tempfile.mkstemp",
                    side_effect=PermissionError,
                ),
                self.assertRaisesRegex(
                    GmailAuthorizationError,
                    "token could not be created",
                ),
            ):
                authorize_gmail(
                    client_secrets,
                    token,
                    flow_class=FakeFlowClass,
                )

            self.assertFalse(token.exists())

    def test_cli_dispatches_without_printing_token_contents(self):
        token_path = Path("data/gmail_token.json")
        output = io.StringIO()
        arguments = [
            "jobhunter",
            "authorize-gmail",
            "--client-secrets", "data/google_client_secret.json",
            "--token", str(token_path),
        ]
        with (
            patch("sys.argv", arguments),
            patch("jobhunter_ai.cli.authorize_gmail", return_value=token_path) as mocked,
            redirect_stdout(output),
        ):
            main()

        mocked.assert_called_once_with(
            "data/google_client_secret.json",
            str(token_path),
        )
        self.assertIn(str(token_path), output.getvalue())
        self.assertNotIn("synthetic-test-token", output.getvalue())


if __name__ == "__main__":
    unittest.main()
