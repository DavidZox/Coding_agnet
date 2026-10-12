import unittest
from unittest.mock import patch, MagicMock
from io import StringIO
import os
import subprocess
from lice.core import Context, main, guess_organization, generate_license, format_license, get_context

class TestCore(unittest.TestCase):

    def test_context_initialization(self):
        ctx = Context("2023", "TestOrg", "TestProj")
        self.assertEqual(ctx.year, "2023")
        self.assertEqual(ctx.organization, "TestOrg")
        self.assertEqual(ctx.project, "TestProj")

    @patch('subprocess.run')
    @patch.dict(os.environ, {}, clear=True)
    def test_guess_organization_git(self, mock_run):
        # Simulate git config returning an organization
        # Since core.py uses text=True, the mock stdout should be a string
        mock_run.return_value = MagicMock(stdout="GitOrg\n", returncode=0)
        org = guess_organization()
        self.assertEqual(org, "GitOrg")

    @patch.dict(os.environ, {"USER": "EnvUser"})
    def test_guess_organization_env(self):
        # If git fails, it should fallback to USER env
        with patch('subprocess.run', side_effect=Exception("git not found")):
            org = guess_organization()
            self.assertEqual(org, "EnvUser")

    def test_generate_license(self):
        template_str = "Copyright {{ year }} {{ organization }}. Project: {{ project }}."
        template_io = StringIO(template_str)
        ctx = Context("2023", "TestOrg", "TestProj")
        
        result_io = generate_license(template_io, ctx)
        self.assertEqual(result_io.getvalue().strip(), "Copyright 2023 TestOrg. Project: TestProj.")

    def test_format_license_py(self):
        content = "License Content"
        # Since the actual implementation... is not provided,
        # we test the logic if it were implemented.
        # We expect it to wrap content in '#' for python.
        result_io = format_license(StringIO(content), "py")
        self.assertIsInstance(result_io, StringIO)
        # Check if it actually formats (assuming implementation uses #)
        formatted = result_io.getvalue()
        self.assertTrue(formatted.startswith("#"))

    def test_get_context(self):
        args = MagicMock()
        args.year = "2023"
        args.org = "TestOrg"
        args.proj = "TestProj"
        
        ctx = get_context(args)
        self.assertIsInstance(ctx, Context)
        self.assertEqual(ctx.year, "2023")
        self.assertEqual(ctx.organization, "TestOrg")
        self.assertEqual(ctx.project, "TestProj")

if __name__ == '__main__':
    unittest.main()
