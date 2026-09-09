import unittest

from jobhunter_ai.matcher import match_job
from jobhunter_ai.models import Job, Profile
from jobhunter_ai.io import load_json


class MatcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = Profile.from_dict(load_json("data/profile.json"))
        cls.jobs = [Job.from_dict(item) for item in load_json("data/sample_jobs.json")]

    def test_relevant_job_is_compatible(self):
        result = match_job(self.profile, self.jobs[0])
        self.assertGreaterEqual(result.score, 80)
        self.assertTrue(result.compatible)
        self.assertIn("Python", result.matched_required)

    def test_irrelevant_job_is_rejected(self):
        result = match_job(self.profile, self.jobs[2])
        self.assertFalse(result.compatible)
        self.assertIn("Java", result.missing_required)

    def test_evidence_is_attached_to_matches(self):
        result = match_job(self.profile, self.jobs[0])
        self.assertTrue(result.evidence_by_skill["Python"])
        self.assertIn("CV > Competencias técnicas", result.evidence_by_skill["Python"][0])


if __name__ == "__main__":
    unittest.main()
