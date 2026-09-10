import unittest

from jobhunter_ai.cli import build_parser
from jobhunter_ai.filters import classify_employment_type, evaluate_job
from jobhunter_ai.io import load_json
from jobhunter_ai.models import Job


def make_job(**overrides) -> Job:
    values = {
        "id": "search-filter-test",
        "title": "Systems Intern",
        "company": "Example Company",
        "location": "Remote",
        "url": "https://example.com/jobs/search-filter-test",
        "description": "Entry-level Linux support role.",
        "required_skills": [],
        "preferred_skills": [],
        "keywords": [],
        "source": "manual",
        "employment_type": "unknown",
        "schedule": "unknown",
        "experience_level": "Entry-level",
    }
    values.update(overrides)
    return Job(**values)


class SearchFilterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preferences = load_json("data/search_preferences.example.json")

    def test_cli_accepts_search_preferences(self):
        args = build_parser().parse_args([
            "run",
            "--profile", "data/profile.example.json",
            "--jobs", "data/sample_jobs.json",
            "--search-preferences", "data/search_preferences.example.json",
        ])

        self.assertEqual(args.search_preferences, "data/search_preferences.example.json")

    def test_hybrid_requires_nuevo_leon_location(self):
        accepted = evaluate_job(
            make_job(location="Monterrey, Nuevo León", description="Hybrid Linux support role."),
            self.preferences,
        )
        rejected = evaluate_job(
            make_job(id="outside-nl", location="Ciudad de México", description="Hybrid Linux support role."),
            self.preferences,
        )

        self.assertTrue(accepted.accepted)
        self.assertIn("modalidad: hybrid", accepted.matched_preferences)
        self.assertTrue(any(item.startswith("ubicación permitida:") for item in accepted.matched_preferences))
        self.assertFalse(rejected.accepted)
        self.assertTrue(any("Ubicación no compatible" in reason for reason in rejected.reasons))

    def test_remote_accepts_any_location(self):
        result = evaluate_job(
            make_job(location="Toronto, Canada", description="Fully remote Python support role."),
            self.preferences,
        )

        self.assertTrue(result.accepted)
        self.assertEqual(result.work_mode, "remote")
        self.assertIn("ubicación: cualquiera por modalidad remota", result.matched_preferences)

    def test_spanish_onsite_mode_is_recognized(self):
        result = evaluate_job(
            make_job(location="Guadalupe, Nuevo León", description="Puesto presencial de soporte técnico."),
            self.preferences,
        )

        self.assertTrue(result.accepted)
        self.assertEqual(result.work_mode, "on-site")

    def test_unknown_work_mode_is_rejected_with_clear_reason(self):
        result = evaluate_job(
            make_job(location="Monterrey", description="Entry-level Linux support role."),
            self.preferences,
        )

        self.assertFalse(result.accepted)
        self.assertEqual(result.work_mode, "unknown")
        self.assertTrue(any("Modalidad no compatible" in reason for reason in result.reasons))

    def test_seniority_uses_only_title_and_experience_level(self):
        description_only = evaluate_job(
            make_job(description="Remote Linux role collaborating with senior stakeholders."),
            self.preferences,
        )
        title_senior = evaluate_job(
            make_job(id="senior-title", title="Senior Systems Intern", description="Remote Linux role."),
            self.preferences,
        )
        level_lead = evaluate_job(
            make_job(id="lead-level", description="Remote Linux role.", experience_level="Lead"),
            self.preferences,
        )

        self.assertTrue(description_only.accepted)
        self.assertFalse(title_senior.accepted)
        self.assertFalse(level_lead.accepted)
        self.assertTrue(any("nivel excluido" in reason for reason in title_senior.reasons))

    def test_full_time_is_rejected_even_when_junior(self):
        result = evaluate_job(
            make_job(
                title="Junior Python Developer de tiempo completo",
                description="Remote entry-level role.",
            ),
            self.preferences,
        )

        self.assertFalse(result.accepted)
        self.assertEqual(result.employment_type, "full-time")
        self.assertTrue(any("Tipo de empleo no compatible" in reason for reason in result.reasons))

    def test_employment_terms_are_recognized_in_english_and_spanish(self):
        cases = {
            "Practicante de sistemas": "internship",
            "Becario de soporte": "internship",
            "Security Intern": "internship",
            "Soporte de medio tiempo": "part-time",
            "Cloud Trainee": "trainee",
            "Aprendiz de redes": "apprenticeship",
            "Puesto para estudiante de TI": "student",
        }

        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(classify_employment_type(make_job(title=title)), expected)

    def test_full_word_matching_avoids_false_positives(self):
        internal = make_job(title="Internal Tools Analyst", employment_type="unknown")
        managerial = evaluate_job(
            make_job(title="Managerial Systems Intern", description="Remote Linux role."),
            self.preferences,
        )
        leadership = evaluate_job(
            make_job(title="Leadership Security Intern", description="Remote Linux role."),
            self.preferences,
        )

        self.assertEqual(classify_employment_type(internal), "unknown")
        self.assertTrue(managerial.accepted)
        self.assertTrue(leadership.accepted)

    def test_technical_role_is_not_limited_to_a_closed_title_list(self):
        result = evaluate_job(
            make_job(
                title="Observability Intern",
                description="Remote role working with Linux, logs and automation.",
            ),
            self.preferences,
        )

        self.assertTrue(result.accepted)
        self.assertIn("área: TI", result.matched_preferences)
        self.assertEqual(result.priority_matches, ["Linux", "automation", "logs"])

    def test_non_it_role_is_rejected_with_clear_reason(self):
        result = evaluate_job(
            make_job(
                title="Marketing Intern",
                description="Remote role creating social media campaigns.",
            ),
            self.preferences,
        )

        self.assertFalse(result.accepted)
        self.assertTrue(any("Área no compatible" in reason for reason in result.reasons))


if __name__ == "__main__":
    unittest.main()
