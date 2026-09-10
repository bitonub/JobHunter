from __future__ import annotations

import re
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import parseaddr
from html.parser import HTMLParser
from pathlib import Path

from ..models import Job
from .base import JobSource


_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_BLOCK_TAGS = {
    "article",
    "blockquote",
    "br",
    "div",
    "footer",
    "h1",
    "h2",
    "h3",
    "header",
    "li",
    "main",
    "ol",
    "p",
    "section",
    "table",
    "td",
    "th",
    "tr",
    "ul",
}


class _BasicHtmlReader(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.chunks: list[str] = []
        self.links: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag in _BLOCK_TAGS:
            self.chunks.append("\n")
        if tag == "a":
            href = dict(attrs).get("href")
            if href and href.lower().startswith(("http://", "https://")):
                self.links.append(href.strip())

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1
            return
        if not self._ignored_depth and tag in _BLOCK_TAGS:
            self.chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.chunks.append(data)

    def text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self.chunks).splitlines()]
        return "\n".join(line for line in lines if line)


class EmailAlertJobSource(JobSource):
    """Convert local RFC 822 job-alert messages into Job objects."""

    def __init__(self, path: str | Path, provider: str | None = None) -> None:
        self.path = Path(path)
        self.provider = provider.strip() if provider else None

    def fetch_jobs(self) -> list[Job]:
        return [self._read_job(path) for path in self._message_paths()]

    def _message_paths(self) -> list[Path]:
        if self.path.is_file():
            if self.path.suffix.lower() != ".eml":
                raise ValueError("email alert file must use the .eml extension")
            return [self.path]
        if self.path.is_dir():
            return sorted(
                path for path in self.path.iterdir()
                if path.is_file() and path.suffix.lower() == ".eml"
            )
        raise FileNotFoundError(f"email alert path does not exist: {self.path}")

    def _read_job(self, path: Path) -> Job:
        message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
        sender = parseaddr(str(message.get("From", "")))[1]
        subject = " ".join(str(message.get("Subject", "")).split())
        description, links = self._message_content(message)
        title = self._labeled_value(
            description,
            ("job title", "title", "vacante", "puesto", "position"),
        )
        company = self._labeled_value(
            description,
            ("company", "empresa", "compañía", "employer"),
        )
        location = self._labeled_value(
            description,
            ("location", "ubicación", "ubicacion", "lugar"),
        )
        subject_title, subject_company = self._subject_details(subject)
        title = title or subject_title
        company = company or subject_company

        return Job(
            id=self._message_id(message, path),
            title=title or "No especificado",
            company=company or "No especificada",
            location=location or "No especificada",
            url=self._application_url(links),
            description=description,
            required_skills=[],
            preferred_skills=[],
            keywords=[],
            source=self._provider(sender),
            employment_type="unknown",
            schedule="unknown",
            experience_level="unknown",
            sender=sender,
            subject=subject,
            links=links,
        )

    @classmethod
    def _message_content(cls, message: Message) -> tuple[str, list[str]]:
        plain_parts: list[str] = []
        html_parts: list[str] = []
        links: list[str] = []
        parts = message.walk() if message.is_multipart() else (message,)

        for part in parts:
            if part.is_multipart() or part.get_content_disposition() == "attachment":
                continue
            content_type = part.get_content_type().lower()
            if content_type not in {"text/plain", "text/html"}:
                continue
            content = cls._part_text(part)
            if content_type == "text/html":
                reader = _BasicHtmlReader()
                reader.feed(content)
                rendered = reader.text()
                if rendered:
                    html_parts.append(rendered)
                links.extend(reader.links)
                links.extend(cls._find_urls(rendered))
            else:
                normalized = cls._normalize_body(content)
                if normalized:
                    plain_parts.append(normalized)
                links.extend(cls._find_urls(content))

        description = "\n".join(plain_parts or html_parts)
        return description, cls._deduplicate(links)

    @staticmethod
    def _part_text(part: Message) -> str:
        try:
            content = part.get_content()
            if isinstance(content, str):
                return content
        except (LookupError, UnicodeDecodeError):
            pass
        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes):
            return str(payload or "")
        return payload.decode(part.get_content_charset() or "utf-8", errors="replace")

    @staticmethod
    def _normalize_body(value: str) -> str:
        lines = [" ".join(line.split()) for line in value.replace("\r\n", "\n").split("\n")]
        return "\n".join(line for line in lines if line)

    @staticmethod
    def _find_urls(value: str) -> list[str]:
        return [match.group(0).rstrip(".,;:!?)") for match in _URL_PATTERN.finditer(value)]

    @staticmethod
    def _deduplicate(values: list[str]) -> list[str]:
        return list(dict.fromkeys(value for value in values if value))

    @staticmethod
    def _labeled_value(text: str, labels: tuple[str, ...]) -> str:
        alternatives = "|".join(re.escape(label) for label in labels)
        match = re.search(rf"(?im)^\s*(?:{alternatives})\s*:\s*(.+?)\s*$", text)
        return " ".join(match.group(1).split()) if match else ""

    @staticmethod
    def _subject_details(subject: str) -> tuple[str, str]:
        prefix = r"(?:job alert|new job|alerta de empleo|nueva vacante)"
        match = re.match(
            rf"(?i)^\s*{prefix}\s*:\s*(?P<title>.+?)\s+(?:at|en)\s+(?P<company>.+?)\s*$",
            subject,
        )
        if match:
            return match.group("title").strip(), match.group("company").strip()
        match = re.match(rf"(?i)^\s*{prefix}\s*:\s*(?P<title>.+?)\s*$", subject)
        return (match.group("title").strip(), "") if match else ("", "")

    @staticmethod
    def _application_url(links: list[str]) -> str:
        ignored = ("unsubscribe", "privacy", "preferences")
        candidates = [link for link in links if not any(term in link.lower() for term in ignored)]
        hints = ("apply", "job", "vacant", "empleo", "position")
        return next(
            (link for link in candidates if any(hint in link.lower() for hint in hints)),
            candidates[0] if candidates else "",
        )

    @staticmethod
    def _message_id(message: Message, path: Path) -> str:
        raw_id = str(message.get("Message-ID", "")).strip().strip("<>") or f"email-{path.stem}"
        return re.sub(r"[^A-Za-z0-9._@-]+", "-", raw_id).strip("-") or f"email-{path.stem}"

    def _provider(self, sender: str) -> str:
        if self.provider:
            return self.provider
        domain = sender.rpartition("@")[2].lower()
        return domain or "unknown"
