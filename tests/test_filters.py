import unittest

from jobhunter_ai.filters import evaluate_job
from jobhunter_ai.io import load_json
from jobhunter_ai.models import Job


class FilterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preferences = load_json("data/preferences.json")
        cls.jobs = [Job.from_dict(item) for item in load_json("data/sample_jobs.json")]

    def test_internship_is_allowed(self):
        result = evaluate_job(self.jobs[0], self.preferences)
        self.assertTrue(result.accepted)
        self.assertEqual(result.employment_type, "internship")

    def test_full_time_is_discarded(self):
        result = evaluate_job(self.jobs[2], self.preferences)
        self.assertFalse(result.accepted)
        self.assertIn("Tipo de empleo no compatible", result.reasons[0])

    def test_senior_keyword_is_discarded(self):
        job = Job.from_dict({
            **load_json("data/sample_jobs.json")[0],
            "id": "senior-intern-test",
            "title": "Senior Security Intern",
        })
        result = evaluate_job(job, self.preferences)
        self.assertFalse(result.accepted)
        self.assertTrue(any("excluido" in reason for reason in result.reasons))


if __name__ == "__main__":
    unittest.main()
