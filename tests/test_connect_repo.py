import unittest
from unittest.mock import patch, MagicMock
from app.routers.repos import parse_repo_identifier

class TestConnectRepo(unittest.TestCase):

    def test_parse_repo_identifier_full_url(self):
        owner, repo = parse_repo_identifier("https://github.com/bhavesh-ashrith-alemela/CodeVanguard")
        self.assertEqual(owner, "bhavesh-ashrith-alemela")
        self.assertEqual(repo, "CodeVanguard")

    def test_parse_repo_identifier_with_git_suffix(self):
        owner, repo = parse_repo_identifier("https://github.com/facebook/react.git")
        self.assertEqual(owner, "facebook")
        self.assertEqual(repo, "react")

    def test_parse_repo_identifier_short_format(self):
        owner, repo = parse_repo_identifier("vercel/next.js")
        self.assertEqual(owner, "vercel")
        self.assertEqual(repo, "next.js")

    def test_parse_repo_identifier_github_domain_no_scheme(self):
        owner, repo = parse_repo_identifier("github.com/torvalds/linux")
        self.assertEqual(owner, "torvalds")
        self.assertEqual(repo, "linux")

    def test_parse_repo_identifier_invalid_host(self):
        with self.assertRaises(ValueError) as ctx:
            parse_repo_identifier("https://evil.com/owner/repo")
        self.assertIn("Only GitHub repositories", str(ctx.exception))

    def test_parse_repo_identifier_invalid_format(self):
        with self.assertRaises(ValueError):
            parse_repo_identifier("invalid-format-without-slash")

        with self.assertRaises(ValueError):
            parse_repo_identifier("too/many/nested/levels")

    def test_parse_repo_identifier_empty(self):
        with self.assertRaises(ValueError):
            parse_repo_identifier("")

    def test_parse_repo_identifier_path_traversal(self):
        with self.assertRaises(ValueError):
            parse_repo_identifier("../evil/repo")

if __name__ == "__main__":
    unittest.main()
