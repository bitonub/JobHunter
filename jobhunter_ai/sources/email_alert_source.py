from __future__ import annotations

import hashlib
import re
from html import unescape
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import parseaddr
from html.parser import HTMLParser
from pathlib import Path

from ..filters import classify_employment_type
from ..job_quality import (
    application_url_key,
    canonical_application_url,
    identify_email_provider,
    select_application_url,
)
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
        self.anchor_records: list[tuple[str, str]] = []
        self._ignored_depth = 0
        self._anchor_href = ""
        self._anchor_chunks: list[str] = []

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
                self._anchor_href = unescape(href.strip())
                self._anchor_chunks = []
                self.links.append(self._anchor_href)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1
            return
        if tag == "a" and self._anchor_href:
            anchor_text = " ".join(" ".join(self._anchor_chunks).split())
            self.anchor_records.append((self._anchor_href, anchor_text))
            self._anchor_href = ""
            self._anchor_chunks = []
        if not self._ignored_depth and tag in _BLOCK_TAGS:
            self.chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.chunks.append(data)
            if self._anchor_href:
                self._anchor_chunks.append(data)

    def text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self.chunks).splitlines()]
        return "\n".join(line for line in lines if line)


class EmailAlertJobSource(JobSource):
    """Convert local RFC 822 job-alert messages into Job objects."""

    def __init__(self, path: str | Path, provider: str | None = None) -> None:
        self.path = Path(path)
        self.provider = provider.strip() if provider else None

    def fetch_jobs(self) -> list[Job]:
        jobs: list[Job] = []
        for path in self._message_paths():
            jobs.extend(self._read_jobs(path))
        return jobs

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

    def _read_jobs(self, path: Path) -> list[Job]:
        return self.parse_jobs(
            path.read_bytes(),
            provider=self.provider,
            fallback_id=f"email-{path.stem}",
        )

    @classmethod
    def parse_bytes(
        cls,
        raw_message: bytes,
        *,
        provider: str | None = None,
        fallback_id: str = "email-message",
    ) -> Job:
        """Parse one RFC 822 job for callers that expect a single result."""

        return cls.parse_jobs(
            raw_message,
            provider=provider,
            fallback_id=fallback_id,
        )[0]

    @classmethod
    def parse_jobs(
        cls,
        raw_message: bytes,
        *,
        provider: str | None = None,
        fallback_id: str = "email-message",
    ) -> list[Job]:
        """Parse one or more jobs from an RFC 822 message entirely in memory."""

        message = BytesParser(policy=policy.default).parsebytes(raw_message)
        sender = parseaddr(str(message.get("From", "")))[1]
        subject = " ".join(str(message.get("Subject", "")).split())
        description, links, html_readers = cls._message_content(message)
        source = cls._provider(sender, provider)
        message_id = cls._message_id(message, fallback_id)
        digest_jobs: list[Job] = []
        for reader in html_readers:
            digest_jobs.extend(
                cls._digest_jobs(reader, message_id, sender, subject, source)
            )
        if digest_jobs:
            return list({job.url: job for job in digest_jobs}.values())

        return [
            cls._single_job(
                message_id,
                sender,
                subject,
                source,
                description,
                links,
            )
        ]

    @classmethod
    def _single_job(
        cls,
        message_id: str,
        sender: str,
        subject: str,
        source: str,
        description: str,
        links: list[str],
    ) -> Job:
        title = cls._labeled_value(
            description,
            ("job title", "title", "vacante", "puesto", "position", "cargo", "role"),
        )
        company = cls._labeled_value(
            description,
            ("company", "empresa", "compañía", "employer", "contratante"),
        )
        location = cls._labeled_value(
            description,
            ("location", "ubicación", "ubicacion", "lugar", "ciudad", "city", "zona"),
        )
        subject_title, subject_company = cls._subject_details(subject)
        title = title or subject_title
        company = company or subject_company

        job = Job(
            id=message_id,
            title=title or "No especificado",
            company=company or "No especificada",
            location=location or "No especificada",
            url=select_application_url(links, source, sender),
            description=description,
            required_skills=[],
            preferred_skills=[],
            keywords=[],
            source=source,
            employment_type="unknown",
            schedule="unknown",
            experience_level="unknown",
            sender=sender,
            subject=subject,
            links=links,
        )
        job.employment_type = classify_employment_type(job)
        if job.employment_type == "part-time":
            job.schedule = "part-time"
        return job

    @classmethod
    def _message_content(
        cls,
        message: Message,
    ) -> tuple[str, list[str], list[_BasicHtmlReader]]:
        plain_parts: list[str] = []
        html_parts: list[str] = []
        html_readers: list[_BasicHtmlReader] = []
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
                html_readers.append(reader)
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

        description = cls._merge_text_parts([*plain_parts, *html_parts])
        return description, cls._deduplicate(links), html_readers

    @classmethod
    def _digest_jobs(
        cls,
        reader: _BasicHtmlReader,
        message_id: str,
        sender: str,
        subject: str,
        source: str,
    ) -> list[Job]:
        provider = identify_email_provider(source, sender)
        grouped: dict[str, dict[str, list[str]]] = {}
        for link, anchor_text in reader.anchor_records:
            key = application_url_key(link, provider)
            if not key:
                continue
            group = grouped.setdefault(key, {"links": [], "titles": []})
            group["links"].append(link)
            if cls._is_title_anchor(anchor_text):
                group["titles"].append(anchor_text)

        candidates: list[tuple[str, str, str]] = []
        for key, group in grouped.items():
            if not group["titles"]:
                continue
            title = max(group["titles"], key=len)
            url = canonical_application_url(group["links"][0], provider)
            if url:
                candidates.append((key, title, url))

        lines = reader.text().splitlines()
        positioned: list[tuple[int, str, str, str]] = []
        cursor = 0
        for key, title, url in candidates:
            position = cls._find_title_line(lines, title, cursor)
            if position is None:
                continue
            positioned.append((position, key, title, url))
            cursor = position + 1

        jobs: list[Job] = []
        for index, (position, key, title, url) in enumerate(positioned):
            end = positioned[index + 1][0] if index + 1 < len(positioned) else len(lines)
            card_lines = lines[position:end]
            company, location, description = cls._digest_card_fields(card_lines, title)
            digest_id = hashlib.sha256(f"{message_id}\n{key}".encode("utf-8")).hexdigest()
            job = Job(
                id=f"email-card-{digest_id[:20]}",
                title=title or "No especificado",
                company=company or "No especificada",
                location=location or "No especificada",
                url=url,
                description=description,
                required_skills=[],
                preferred_skills=[],
                keywords=[],
                source=source,
                employment_type="unknown",
                schedule="unknown",
                experience_level="unknown",
                sender=sender,
                subject=subject,
                links=[url],
            )
            job.employment_type = classify_employment_type(job)
            if job.employment_type == "part-time":
                job.schedule = "part-time"
            jobs.append(job)
        return jobs

    @staticmethod
    def _is_title_anchor(value: str) -> bool:
        normalized = " ".join(value.split())
        if not 3 <= len(normalized) <= 180:
            return False
        return re.match(
            r"(?i)^(?:apply|apply now|view|view job|view original job|ver|ver vacante|"
            r"postular|postúlate|save|guardar)\b",
            normalized,
        ) is None

    @staticmethod
    def _find_title_line(lines: list[str], title: str, start: int) -> int | None:
        normalized_title = " ".join(title.casefold().split())
        for index in range(start, len(lines)):
            normalized_line = " ".join(lines[index].casefold().split())
            if normalized_line == normalized_title or normalized_title in normalized_line:
                return index
        return None

    @classmethod
    def _digest_card_fields(
        cls,
        lines: list[str],
        title: str,
    ) -> tuple[str, str, str]:
        text = "\n".join(lines)
        company = cls._labeled_value(
            text,
            ("company", "empresa", "compañía", "employer", "contratante"),
        )
        location = cls._labeled_value(
            text,
            ("location", "ubicación", "ubicacion", "lugar", "ciudad", "city", "zona"),
        )
        remaining: list[str] = []
        metadata = re.compile(
            r"(?i)^(?:company|empresa|compañía|employer|contratante|location|ubicación|"
            r"ubicacion|lugar|ciudad|city|zona)\s*:"
        )
        boilerplate = re.compile(
            r"(?i)^(?:apply|view|ver|postular|postúlate|save|guardar|promoted|"
            r"be an early applicant|actively recruiting)\b"
        )
        for line in lines:
            normalized = " ".join(line.split())
            if not normalized or normalized.casefold() == title.casefold():
                continue
            if metadata.match(normalized) or boilerplate.match(normalized):
                continue
            if normalized.lower().startswith(("http://", "https://")):
                continue
            remaining.extend(
                part.strip() for part in re.split(r"\s+[·|]\s+", normalized) if part.strip()
            )
        if not company and remaining:
            company = remaining.pop(0)
        if not location and remaining:
            location = remaining.pop(0)
        return company, location, "\n".join(remaining)

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
        return [
            unescape(match.group(0)).rstrip(".,;:!?)")
            for match in _URL_PATTERN.finditer(value)
        ]

    @staticmethod
    def _merge_text_parts(parts: list[str]) -> str:
        lines: list[str] = []
        seen: set[str] = set()
        for part in parts:
            for line in part.splitlines():
                normalized = " ".join(line.split())
                key = normalized.casefold()
                if normalized and key not in seen:
                    lines.append(normalized)
                    seen.add(key)
        return "\n".join(lines)

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
        prefix = (
            r"(?:job alert|new job|recommended job|alerta de empleo|nueva vacante|"
            r"nuevo empleo|empleo recomendado)"
        )
        match = re.match(
            rf"(?i)^\s*{prefix}\s*:\s*(?P<title>.+?)\s+(?:at|en)\s+(?P<company>.+?)\s*$",
            subject,
        )
        if match:
            return match.group("title").strip(), match.group("company").strip()
        match = re.match(rf"(?i)^\s*{prefix}\s*:\s*(?P<title>.+?)\s*$", subject)
        return (match.group("title").strip(), "") if match else ("", "")

    @staticmethod
    def _message_id(message: Message, fallback_id: str) -> str:
        raw_id = str(message.get("Message-ID", "")).strip().strip("<>") or fallback_id
        return re.sub(r"[^A-Za-z0-9._@-]+", "-", raw_id).strip("-") or fallback_id

    @staticmethod
    def _provider(sender: str, provider: str | None = None) -> str:
        if provider:
            return provider.strip()
        domain = sender.rpartition("@")[2].lower()
        return domain or "unknown"
