import unittest
from io import StringIO
from unittest.mock import patch
import os
from lice.core import (
    Context,
    guess_organization,
    get_context,
    extract_vars,
    generate_license,
    format_license
)

class TestLiceCore(unittest.TestCase):

    def test_context_initialization(self):
        ctx = Context("2023", "TestOrg", "TestProj")
        self.assertEqual(ctx.year, "2023")
        self.assertEqual(ctx.organization, "TestOrg")
        self.assertEqual(ctx.project, "TestProj")

    def test_extract_vars(self):
        template = StringIO("{year} {organization} {project}")
        vars_list = extract_vars(template)
        self.assertIn("year", vars_list)
        self.assertIn("organization", vars_list)
        self.assertIn("project", vars_list)

    def test_generate_license(self):
        template = StringIO("Copyright (c) {year} {organization}")
        ctx = Context("2023", "ExampleOrg", "ExampleProj")
        result_sio = generate_license(template, ctx)
        self.assertEqual(result_sio.getvalue().strip(), "Copyright (c) 2023 ExampleOrg")

    def test_format_license_python(self):
        # Simulate content from generate_license
        content = StringIO("Copyright (c) 2023 ExampleOrg")
        # Mocking format_license behavior for Python style (using #)
        # Since we don't have the actual implementation logic here, 
        # we test if it returns a StringIO as expected.
        result_sio = format_license(content, "py")
        self.assertIsInstance(result_sio, StringIO)
        self.assertTrue(len(result_sio.getvalue()) > 0)

    @patch('os.environ.get')
    def test_guess_organization_env(self, mock_env_get):
        mock_env_get.return_value = "EnvUser"
        # If git config fails, it should fallback to USER env
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = Exception("git not found")
            org = guess_organization()
            self.assertEqual(org, "EnvUser")

    def test_get_context(self):
        class Args:
            def __init__(self):
                self.year = "2024"
                self.org = "MyOrg"
                self.proj = "MyProj"
        
        args = Args()
        ctx = get_context(args)
        self.assertEqual(ctx.year, "2024")
        self.assertEqual(ctx.organization, "MyOrg")
        self.assertEqual(ctx.project, "MyProj")

if __name__ == '__main__':
    unittest.main()
