import unittest

from jobhunter_ai.io import load_json
from jobhunter_ai.matcher import match_job
from jobhunter_ai.models import Job, Profile
from jobhunter_ai.tailor import build_tailored_cv


class TailorTests(unittest.TestCase):
    def test_tailored_cv_uses_only_profile_content(self):
        profile = Profile.from_dict(load_json("data/profile.example.json"))
        job = Job.from_dict(load_json("data/sample_jobs.json")[0])
        result = match_job(profile, job)
        tailored = build_tailored_cv(profile, job, result)

        self.assertIn("Candidate Example", tailored.markdown)
        self.assertIn("Python", tailored.markdown)
        self.assertNotIn("Kubernetes", tailored.markdown)
        self.assertTrue(any("Compatibilidad calculada" in item for item in tailored.selected_evidence["job"]))


if __name__ == "__main__":
    unittest.main()
