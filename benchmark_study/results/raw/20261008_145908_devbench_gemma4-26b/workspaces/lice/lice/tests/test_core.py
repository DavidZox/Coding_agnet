import unittest
from io import StringIO
from unittest.mock import patch
from lice.core import Context, guess_organization, generate_license

class TestCore(unittest.TestCase):

    def test_context_initialization(self):
        """Test if Context correctly stores and returns values."""
        ctx = Context("2023", "TestOrg", "TestProj")
        self.assertEqual(ctx.year, "2023")
        self.assertEqual(ctx.organization, "TestOrg")
        self.assertEqual(ctx.project, "TestProj")

    @patch('subprocess.check_output')
    @patch('os.environ.get')
    def test_guess_organization_git(self, mock_env_get, mock_subprocess):
        """Test guessing organization from git config."""
        # Mock git config success
        mock_subprocess.return_value = b"GitOrg\n"
        org = guess_organization()
        self.assertEqual(org, "GitOrg")

    @patch('os.environ.get')
    def test_guess_organization_env(self, mock_env_get):
        """Test guessing organization from USER environment variable if git fails."""
        # Mock git config failure (subprocess error)
        with patch('subprocess.check_output', side_effect=Exception("git error")):
            # Mock USER env variable
            mock_env_get.side_effect = lambda k, default=None: "EnvUser" if k == "USER" else default
            org = guess_organization()
            self.assertEqual(org, "EnvUser")

    def test_generate_license(self):
        """Test license generation with template variables."""
        template_content = "Copyright (c) {{year}} {{organization}}. Project: {{project}}."
        template_io = StringIO(template_content)
        ctx = Context("2024", "MyOrg", "MyApp")
        
        result_io = generate_license(template_io, ctx)
        result_text = result_io.getvalue()
        
        self.assertEqual(result_text, "Copyright (c) 2024 MyOrg. Project: MyApp.")

if __name__ == '__main__':
    unittest.main()
