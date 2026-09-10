from __future__ import annotations

from typing import Any


def build_diagnostic_summary(
    filtered_out: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
    threshold: float,
) -> dict[str, Any]:
    """Summarize filter and matching outcomes without changing them."""

    discarded_by_employment_type = 0
    discarded_by_excluded_keyword = 0
    discarded_by_unknown_employment_type = 0
    discarded_examples: list[dict[str, str]] = []

    for item in filtered_out:
        filter_data = item.get("filter", {})
        reasons = [str(reason) for reason in filter_data.get("reasons", [])]
        has_employment_type_reason = any(
            reason.startswith("Tipo de empleo no compatible:") for reason in reasons
        )
        has_excluded_keyword_reason = any(
            reason.startswith("Palabra o nivel excluido:") for reason in reasons
        )
        if has_employment_type_reason:
            discarded_by_employment_type += 1
        if has_excluded_keyword_reason:
            discarded_by_excluded_keyword += 1
        if has_employment_type_reason and filter_data.get("employment_type") == "unknown":
            discarded_by_unknown_employment_type += 1

        if len(discarded_examples) < 10:
            job = item.get("job", {})
            discarded_examples.append(
                {
                    "title": str(job.get("title", "")),
                    "company": str(job.get("company", "")),
                    "employment_type": str(filter_data.get("employment_type", "unknown")),
                    "reason": "; ".join(reasons),
                }
            )

    scores = [
        float(item["analysis"]["score"])
        for item in alerts
        if "analysis" in item and "score" in item["analysis"]
    ]
    passed_filter_score = {
        "count": len(scores),
        "average": round(sum(scores) / len(scores), 2) if scores else None,
        "minimum": min(scores) if scores else None,
        "maximum": max(scores) if scores else None,
    }

    return {
        "discarded_by_employment_type": discarded_by_employment_type,
        "discarded_by_excluded_keyword": discarded_by_excluded_keyword,
        "discarded_by_unknown_employment_type": discarded_by_unknown_employment_type,
        "passed_filters_below_threshold": sum(
            not item.get("analysis", {}).get("compatible", False) for item in alerts
        ),
        "threshold": threshold,
        "passed_filter_score": passed_filter_score,
        "discarded_examples": discarded_examples,
    }
