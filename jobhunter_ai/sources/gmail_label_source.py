from __future__ import annotations

import base64
import binascii
from email.utils import parseaddr
from pathlib import Path
from typing import Any, Iterable

from ..models import Job
from .base import JobSource
from .email_alert_source import EmailAlertJobSource


GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_SCOPES = (GMAIL_READONLY_SCOPE,)
DEFAULT_GMAIL_LABEL = "JobHunter/Alertas"
DEFAULT_MAX_MESSAGES = 50


class GmailLabelNotFoundError(ValueError):
    """Raised when the configured Gmail label name cannot be resolved."""


class GmailLabelJobSource(JobSource):
    """Read RFC 822 job alerts from one Gmail label without modifying messages."""

    def __init__(
        self,
        token_path: str | Path | None,
        allowed_sender_domains: Iterable[str] | None,
        *,
        label_name: str = DEFAULT_GMAIL_LABEL,
        max_messages: int = DEFAULT_MAX_MESSAGES,
        service: Any | None = None,
    ) -> None:
        self.token_path = Path(token_path) if token_path else None
        self.allowed_sender_domains = self._normalize_domains(allowed_sender_domains)
        self.label_name = label_name.strip()
        self.max_messages = int(max_messages)
        self._service = service
        self.discarded_messages: list[dict[str, str]] = []

        if not self.label_name:
            raise ValueError("Gmail label name cannot be empty")
        if not self.allowed_sender_domains:
            raise ValueError("at least one allowed Gmail sender domain is required")
        if not 1 <= self.max_messages <= 500:
            raise ValueError("Gmail max_messages must be between 1 and 500")

    def fetch_jobs(self) -> list[Job]:
        self.discarded_messages = []
        service = self._service if self._service is not None else self._build_service()
        label_id = self._resolve_label_id(service)
        response = (
            service.users()
            .messages()
            .list(
                userId="me",
                labelIds=[label_id],
                maxResults=self.max_messages,
            )
            .execute()
        )
        summaries = (response.get("messages") or [])[: self.max_messages]
        jobs: list[Job] = []

        for summary in summaries:
            message_id = str(summary.get("id", "")).strip()
            if not message_id:
                continue
            metadata = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=message_id,
                    format="metadata",
                    metadataHeaders=["From"],
                )
                .execute()
            )
            sender_domain = self._sender_domain_from_metadata(metadata)
            if not self._is_allowed_domain(sender_domain):
                self._record_disallowed_sender(sender_domain)
                continue
            payload = (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="raw")
                .execute()
            )
            raw_message = self._decode_raw(payload.get("raw"))
            parsed_jobs = EmailAlertJobSource.parse_jobs(
                raw_message,
                fallback_id=f"gmail-{message_id}",
            )
            parsed_sender_domain = parsed_jobs[0].sender.rpartition("@")[2].lower()
            if not self._is_allowed_domain(parsed_sender_domain):
                self._record_disallowed_sender(parsed_sender_domain)
                continue
            jobs.extend(parsed_jobs)
        return jobs

    @staticmethod
    def _sender_domain_from_metadata(payload: dict[str, Any]) -> str:
        headers = (payload.get("payload") or {}).get("headers") or []
        sender = next(
            (
                str(header.get("value", ""))
                for header in headers
                if str(header.get("name", "")).lower() == "from"
            ),
            "",
        )
        address = parseaddr(sender)[1]
        return address.rpartition("@")[2].lower()

    def _record_disallowed_sender(self, sender_domain: str) -> None:
        self.discarded_messages.append(
            {
                "sender_domain": sender_domain or "unknown",
                "reason": (
                    "Dominio de remitente no permitido: "
                    f"{sender_domain or 'desconocido'}."
                ),
            }
        )

    def _resolve_label_id(self, service: Any) -> str:
        response = service.users().labels().list(userId="me").execute()
        for label in response.get("labels") or []:
            if label.get("name") == self.label_name and label.get("id"):
                return str(label["id"])
        raise GmailLabelNotFoundError(
            f"Gmail label not found: {self.label_name}"
        )

    def _build_service(self) -> Any:
        if self.token_path is None or not self.token_path.is_file():
            raise FileNotFoundError("Gmail OAuth token file was not found")
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError as error:
            raise RuntimeError("Google Gmail API dependencies are not installed") from error

        credentials = Credentials.from_authorized_user_file(
            str(self.token_path),
            scopes=list(GMAIL_SCOPES),
        )
        self._validate_scopes(credentials)
        if not credentials.valid:
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
                self._validate_scopes(credentials)
            else:
                raise RuntimeError("Gmail OAuth authorization is required")
        return build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False,
        )

    @staticmethod
    def _validate_scopes(credentials: Any) -> None:
        granted = getattr(credentials, "granted_scopes", None) or getattr(
            credentials,
            "scopes",
            None,
        )
        if granted and set(granted) != set(GMAIL_SCOPES):
            raise RuntimeError("Gmail OAuth token must grant only gmail.readonly")

    @staticmethod
    def _decode_raw(value: object) -> bytes:
        if not isinstance(value, str) or not value:
            raise ValueError("Gmail message is missing RFC 822 raw data")
        padding = "=" * (-len(value) % 4)
        try:
            return base64.b64decode(
                (value + padding).encode("ascii"),
                altchars=b"-_",
                validate=True,
            )
        except (binascii.Error, UnicodeEncodeError, ValueError, TypeError) as error:
            raise ValueError("Gmail message contains invalid RFC 822 raw data") from error

    @staticmethod
    def _normalize_domains(values: Iterable[str] | None) -> tuple[str, ...]:
        domains: list[str] = []
        if values is None:
            return ()
        source_values = [values] if isinstance(values, str) else values
        for value in source_values:
            for item in str(value).split(","):
                domain = item.strip().lower().lstrip("@").rstrip(".")
                if domain and domain not in domains:
                    domains.append(domain)
        return tuple(domains)

    def _is_allowed_domain(self, sender_domain: str) -> bool:
        return any(
            sender_domain == allowed or sender_domain.endswith(f".{allowed}")
            for allowed in self.allowed_sender_domains
        )
