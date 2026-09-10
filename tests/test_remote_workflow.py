import unittest
from pathlib import Path


class RemoteWorkflowTests(unittest.TestCase):
    def test_optional_search_preferences_secret_has_safe_fallback_and_cleanup(self):
        workflow = Path(".github/workflows/job-search.yml").read_text(encoding="utf-8")

        self.assertIn("SEARCH_PREFERENCES_JSON: ${{ secrets.SEARCH_PREFERENCES_JSON }}", workflow)
        self.assertIn('if [[ -n "${SEARCH_PREFERENCES_JSON:-}" ]]', workflow)
        self.assertIn('printf \'%s\' "$SEARCH_PREFERENCES_JSON" > data/search_preferences.json', workflow)
        self.assertIn("chmod 600 data/search_preferences.json", workflow)
        self.assertIn("preference_args=(--preferences data/preferences.json)", workflow)
        self.assertIn(
            "preference_args=(--search-preferences data/search_preferences.json)",
            workflow,
        )
        self.assertIn("rm -f -- data/profile.json data/search_preferences.json", workflow)
        self.assertNotIn('echo "$SEARCH_PREFERENCES_JSON"', workflow)
        self.assertNotIn("set -x", workflow)


if __name__ == "__main__":
    unittest.main()
