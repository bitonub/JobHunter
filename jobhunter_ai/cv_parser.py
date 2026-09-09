from __future__ import annotations

from pathlib import Path


def extract_text_from_pdf(path: str | Path) -> str:
    """Extract text from a text-based PDF.

    pdfplumber is optional at import time so the matching engine can still run
    with a structured profile in minimal environments.
    """

    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError(
            "Para leer PDF instala las dependencias del proyecto: pip install -e ."
        ) from exc

    pages: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return "\n\n".join(pages).strip()
