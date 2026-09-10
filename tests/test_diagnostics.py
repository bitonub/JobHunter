import unittest

from jobhunter_ai.diagnostics import build_diagnostic_summary


class DiagnosticSummaryTests(unittest.TestCase):
    def test_counts_filter_reasons_scores_and_examples(self):
        filtered_out = [
            {
                "job": {"title": "Senior Engineer", "company": "Example One"},
                "filter": {
                    "employment_type": "full-time",
                    "reasons": ["Tipo de empleo no compatible: full-time."],
                },
            },
            {
                "job": {"title": "Unclassified Role", "company": "Example Two"},
                "filter": {
                    "employment_type": "unknown",
                    "reasons": [
                        "Tipo de empleo no compatible: unknown.",
                        "Palabra o nivel excluido: senior.",
                    ],
                },
            },
            {
                "job": {"title": "Excluded Role", "company": "Example Three"},
                "filter": {
                    "employment_type": "internship",
                    "reasons": ["Palabra o nivel excluido: manager."],
                },
            },
        ]
        alerts = [
            {"analysis": {"score": 55.0, "compatible": False}},
            {"analysis": {"score": 82.5, "compatible": True}},
        ]

        summary = build_diagnostic_summary(filtered_out, alerts, threshold=60.0)

        self.assertEqual(summary["discarded_by_employment_type"], 2)
        self.assertEqual(summary["discarded_by_excluded_keyword"], 2)
        self.assertEqual(summary["discarded_by_unknown_employment_type"], 1)
        self.assertEqual(summary["passed_filters_below_threshold"], 1)
        self.assertEqual(summary["passed_filter_score"]["count"], 2)
        self.assertEqual(summary["passed_filter_score"]["average"], 68.75)
        self.assertEqual(summary["passed_filter_score"]["minimum"], 55.0)
        self.assertEqual(summary["passed_filter_score"]["maximum"], 82.5)
        self.assertEqual(len(summary["discarded_examples"]), 3)
        self.assertEqual(
            set(summary["discarded_examples"][0]),
            {"title", "company", "employment_type", "reason"},
        )

    def test_limits_discarded_examples_to_ten(self):
        filtered_out = [
            {
                "job": {"title": f"Role {index}", "company": "Example"},
                "filter": {
                    "employment_type": "unknown",
                    "reasons": ["Tipo de empleo no compatible: unknown."],
                },
            }
            for index in range(12)
        ]

        summary = build_diagnostic_summary(filtered_out, [], threshold=60.0)

        self.assertEqual(len(summary["discarded_examples"]), 10)


if __name__ == "__main__":
    unittest.main()
