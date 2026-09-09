from __future__ import annotations

import argparse
from pathlib import Path

from .cv_parser import extract_text_from_pdf
from .pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="JobHunter AI - MVP transparente de matching laboral")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_cv = subparsers.add_parser("parse-cv", help="Extrae el texto de un CV PDF")
    parse_cv.add_argument("pdf")
    parse_cv.add_argument("--output", default="output/cv_extraido.txt")

    run = subparsers.add_parser("run", help="Analiza vacantes y genera CVs adaptados")
    run.add_argument("--profile", required=True, help="Perfil estructurado derivado del CV")
    run.add_argument("--jobs", required=True, help="Vacantes en JSON")
    run.add_argument("--output", default="output")
    run.add_argument("--threshold", type=float, default=60.0)
    run.add_argument("--preferences", default="data/preferences.json", help="Preferencias de búsqueda en JSON")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "parse-cv":
        text = extract_text_from_pdf(args.pdf)
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
        print(f"Texto extraído en: {destination}")
        return

    report = run_pipeline(
        args.profile,
        args.jobs,
        args.output,
        threshold=args.threshold,
        preferences_path=args.preferences,
    )
    print(f"Vacantes analizadas: {report['total_jobs']}")
    print(f"Vacantes descartadas por filtros: {report['filtered_out_jobs']}")
    print(f"Vacantes compatibles: {report['compatible_jobs']}")
    print(f"Reporte: {Path(args.output) / 'alerts.json'}")


if __name__ == "__main__":
    main()
