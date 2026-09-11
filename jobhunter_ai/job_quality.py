from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from urllib.parse import parse_qs, unquote, urlsplit, urlunsplit

from .models import Job


_PROVIDER_HOSTS = {
    "occ": ("occ.com.mx",),
    "indeed": ("indeed.com", "indeed.com.mx"),
    "linkedin": ("linkedin.com",),
}
_APPLICATION_HINTS = {
    "occ": ("/empleo/", "/empleos/", "/vacante/", "/trabajo/", "/oferta/"),
    "indeed": ("/viewjob", "/rc/clk", "/pagead/clk", "/jobs/"),
    "linkedin": ("/jobs/view/", "/comm/jobs/view/"),
}
_MISSING_VALUES = {
    "",
    "unknown",
    "not specified",
    "no description available",
    "description not available",
    "no especificado",
    "no especificada",
    "sin descripción",
    "sin descripcion",
    "confidential",
    "confidencial",
    "sin especificar",
}


@dataclass(frozen=True)
class JobQualityResult:
    applicable: bool
    accepted: bool
    provider: str
    missing_fields: list[str]
    rejected_synthetic_links: int
    reasons: list[str]

    def to_dict(self) -> dict:
        return asdict(self)

    def to_filter_dict(self, job: Job) -> dict:
        return {
            "job_id": job.id,
            "accepted": False,
            "employment_type": job.employment_type,
            "work_mode": "unknown",
            "reasons": self.reasons,
            "matched_preferences": [],
            "it_matches": [],
            "priority_matches": [],
        }


def identify_email_provider(source: str, sender: str = "") -> str:
    value = f"{source} {sender}".lower()
    if "linkedin" in value:
        return "linkedin"
    if "indeed" in value:
        return "indeed"
    if "occ" in value:
        return "occ"
    return "unknown"


def is_synthetic_url(value: str) -> bool:
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    lowered = value.lower()
    if not host:
        return False
    return (
        host in {"example.com", "example.org", "example.net"}
        or host.endswith((".example.com", ".example.org", ".example.net"))
        or host.endswith((".example", ".test", ".invalid"))
        or host in {"localhost", "127.0.0.1", "::1"}
        or any(marker in lowered for marker in ("synthetic", "fixture", "placeholder", "dummy"))
    )


def application_url_issue(value: str, provider: str) -> str | None:
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return "URL inválida"
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return "URL no HTTP/HTTPS"
    if is_synthetic_url(value):
        return "Enlace sintético rechazado"
    if provider not in _PROVIDER_HOSTS:
        return "Proveedor de alerta desconocido"

    host = parsed.hostname.lower().rstrip(".")
    if not any(host == allowed or host.endswith(f".{allowed}") for allowed in _PROVIDER_HOSTS[provider]):
        return f"El enlace no pertenece a {provider}"

    target = unquote(f"{parsed.path}?{parsed.query}").lower()
    if not any(hint in target for hint in _APPLICATION_HINTS[provider]):
        return "El enlace no identifica una vacante"
    return None


def select_application_url(links: list[str], source: str, sender: str = "") -> str:
    provider = identify_email_provider(source, sender)
    return next(
        (link for link in links if application_url_issue(link, provider) is None),
        "",
    )


def application_url_key(value: str, provider: str) -> str:
    if application_url_issue(value, provider) is not None:
        return ""
    parsed = urlsplit(value)
    path = unquote(parsed.path)
    if provider == "linkedin":
        match = re.search(r"/(?:comm/)?jobs/view/(\d+)", path, re.IGNORECASE)
        return f"linkedin:{match.group(1)}" if match else ""
    if provider == "indeed":
        job_key = (parse_qs(parsed.query).get("jk") or [""])[0]
        return f"indeed:{job_key}" if job_key else urlunsplit(("", parsed.netloc, path, "", ""))
    if provider == "occ":
        return f"occ:{path.rstrip('/').lower()}"
    return ""


def canonical_application_url(value: str, provider: str) -> str:
    key = application_url_key(value, provider)
    if not key:
        return ""
    parsed = urlsplit(value)
    if provider == "linkedin":
        return f"https://www.linkedin.com/jobs/view/{key.removeprefix('linkedin:')}"
    if provider == "indeed" and key.startswith("indeed:"):
        return urlunsplit(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                parsed.path,
                f"jk={key.removeprefix('indeed:')}",
                "",
            )
        )
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path,
            "",
            "",
        )
    )


def evaluate_email_job_quality(job: Job) -> JobQualityResult:
    provider = identify_email_provider(job.source, job.sender)
    applicable = bool(
        job.sender
        or job.subject
        or job.links
        or provider != "unknown"
        or job.source.lower() == "unknown"
        or job.id.lower().startswith(("email-", "gmail-"))
    )
    if not applicable:
        return JobQualityResult(
            applicable=False,
            accepted=True,
            provider="unknown",
            missing_fields=[],
            rejected_synthetic_links=0,
            reasons=[],
        )

    synthetic_links = sum(is_synthetic_url(link) for link in job.links)
    missing_fields: list[str] = []
    if _is_missing(job.title):
        missing_fields.append("título")
    if _is_missing(job.company):
        missing_fields.append("empresa")
    if not job.url or application_url_issue(job.url, provider) is not None:
        missing_fields.append("URL de postulación real")
    if _description_is_insufficient(job.description):
        missing_fields.append("descripción")

    reasons: list[str] = []
    if synthetic_links:
        reasons.append(
            f"Enlaces sintéticos rechazados: {synthetic_links}; no se usarán para postulación."
        )
    if missing_fields:
        reasons.append(f"Datos insuficientes: falta {', '.join(missing_fields)}.")

    return JobQualityResult(
        applicable=True,
        accepted=not missing_fields,
        provider=provider,
        missing_fields=missing_fields,
        rejected_synthetic_links=synthetic_links,
        reasons=reasons,
    )


def _is_missing(value: str) -> bool:
    return " ".join(value.lower().split()).strip(" .:-") in _MISSING_VALUES


def _description_is_insufficient(value: str) -> bool:
    meaningful_lines: list[str] = []
    metadata_pattern = re.compile(
        r"^(?:job title|title|vacante|puesto|position|cargo|role|company|empresa|"
        r"compañía|employer|contratante|location|ubicación|ubicacion|lugar|ciudad|"
        r"city|zona|modalidad|work mode|tipo de empleo|employment type)\s*:\s*",
        re.IGNORECASE,
    )
    call_to_action = re.compile(
        r"^(?:apply now|view job|view original job|consulta la vacante|postúlate|"
        r"postulate|ver vacante)(?:\b|\s|:)",
        re.IGNORECASE,
    )
    for raw_line in value.splitlines():
        line = " ".join(raw_line.split())
        if not line or metadata_pattern.match(line) or call_to_action.match(line):
            continue
        without_urls = re.sub(r"https?://\S+", "", line, flags=re.IGNORECASE).strip()
        if without_urls:
            meaningful_lines.append(without_urls)
    normalized = " ".join(meaningful_lines)
    return len(normalized) < 20 or normalized.lower() in _MISSING_VALUES
