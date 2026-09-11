from __future__ import annotations

import argparse
from pathlib import Path

from .cv_parser import extract_text_from_pdf
from .gmail_oauth import GmailAuthorizationError, authorize_gmail
from .pipeline import run_pipeline
from .sources import (
    EmailAlertJobSource,
    GmailLabelJobSource,
    JsonJobSource,
    RssJobSource,
    load_configured_source,
)
from .storage import SQLiteJobStateStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="JobHunter AI - MVP transparente de matching laboral")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_cv = subparsers.add_parser("parse-cv", help="Extrae el texto de un CV PDF")
    parse_cv.add_argument("pdf")
    parse_cv.add_argument("--output", default="output/cv_extraido.txt")

    authorize = subparsers.add_parser(
        "authorize-gmail",
        help="Autoriza Gmail localmente y crea un token OAuth privado",
    )
    authorize.add_argument(
        "--client-secrets",
        required=True,
        help="OAuth Client ID de escritorio descargado desde Google Cloud",
    )
    authorize.add_argument(
        "--token",
        required=True,
        help="Ruta privada donde se guardará el token OAuth",
    )

    run = subparsers.add_parser("run", help="Analiza vacantes y genera CVs adaptados")
    run.add_argument("--profile", required=True, help="Perfil estructurado derivado del CV")
    jobs_source = run.add_mutually_exclusive_group(required=True)
    jobs_source.add_argument("--jobs", help="Vacantes en JSON")
    jobs_source.add_argument("--rss-url", help="URL de un feed RSS o Atom")
    jobs_source.add_argument("--sources", help="Lista JSON de fuentes RSS/Atom/JSON/email/Gmail")
    jobs_source.add_argument("--email-alerts", help="Archivo .eml o carpeta con alertas por correo")
    jobs_source.add_argument("--gmail-token", help="Token OAuth local para leer alertas de Gmail")
    run.add_argument("--gmail-label", default="JobHunter/Alertas", help="Nombre de etiqueta de Gmail")
    run.add_argument(
        "--gmail-allowed-domain",
        action="append",
        default=[],
        help="Dominio permitido; puede repetirse o contener valores separados por comas",
    )
    run.add_argument("--gmail-max-messages", type=int, default=50, help="Máximo de mensajes de Gmail")
    run.add_argument("--output", default="output")
    run.add_argument("--state-db", help="Base SQLite opcional para historial y deduplicación")
    run.add_argument("--threshold", type=float, default=60.0)
    run.add_argument("--job-terms", default="data/job_terms.json", help="Catálogo de términos técnicos en JSON")
    run.add_argument("--preferences", default="data/preferences.json", help="Preferencias de búsqueda en JSON")
    run.add_argument(
        "--search-preferences",
        help="Preferencias avanzadas de búsqueda en JSON; reemplaza --preferences",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "parse-cv":
        text = extract_text_from_pdf(args.pdf)
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
        print(f"Texto extraído en: {destination}")
        return

    if args.command == "authorize-gmail":
        try:
            destination = authorize_gmail(args.client_secrets, args.token)
        except (FileNotFoundError, GmailAuthorizationError) as error:
            parser.error(str(error))
        print(f"Autorización de Gmail completada. Token guardado en: {destination}")
        return

    if args.sources:
        source = load_configured_source(args.sources)
    elif args.rss_url:
        source = RssJobSource(args.rss_url)
    elif args.email_alerts:
        source = EmailAlertJobSource(args.email_alerts)
    elif args.gmail_token:
        source = GmailLabelJobSource(
            args.gmail_token,
            args.gmail_allowed_domain,
            label_name=args.gmail_label,
            max_messages=args.gmail_max_messages,
        )
    else:
        source = JsonJobSource(args.jobs)
    state_store = SQLiteJobStateStore(args.state_db) if args.state_db else None
    try:
        report = run_pipeline(
            args.profile,
            source,
            args.output,
            threshold=args.threshold,
            preferences_path=args.search_preferences or args.preferences,
            job_terms_path=args.job_terms,
            state_store=state_store,
        )
    finally:
        if state_store is not None:
            state_store.close()
    print(f"Vacantes analizadas: {report['total_jobs']}")
    print(f"Vacantes nuevas: {report['new_jobs']}")
    print(f"Vacantes vistas anteriormente: {report['previously_seen_jobs']}")
    print(f"Vacantes descartadas por filtros: {report['filtered_out_jobs']}")
    print(f"Vacantes compatibles: {report['compatible_jobs']}")
    diagnostics = report["diagnostics"]
    print(f"Descartadas por tipo de empleo: {diagnostics['discarded_by_employment_type']}")
    print(f"Descartadas por palabras excluidas: {diagnostics['discarded_by_excluded_keyword']}")
    print(f"Descartadas por tipo de empleo desconocido: {diagnostics['discarded_by_unknown_employment_type']}")
    print(f"Enlaces sintéticos rechazados: {diagnostics['rejected_synthetic_links']}")
    print(f"Vacantes con datos insuficientes: {diagnostics['insufficient_data_jobs']}")
    print(f"Pasaron filtros pero no alcanzaron el umbral: {diagnostics['passed_filters_below_threshold']}")
    score_summary = diagnostics["passed_filter_score"]
    if score_summary["count"]:
        print(
            "Score de vacantes que pasaron filtros: "
            f"promedio {score_summary['average']:.2f}% "
            f"(mínimo {score_summary['minimum']:.2f}%, máximo {score_summary['maximum']:.2f}%)"
        )
    else:
        print("Score de vacantes que pasaron filtros: sin vacantes")
    for example in diagnostics["discarded_examples"]:
        print(
            "Ejemplo descartado: "
            f"{example['title']} — {example['company']} — "
            f"{example['employment_type']} — {example['reason']}"
        )
    print(f"Reporte: {Path(args.output) / 'alerts.json'}")


if __name__ == "__main__":
    main()
