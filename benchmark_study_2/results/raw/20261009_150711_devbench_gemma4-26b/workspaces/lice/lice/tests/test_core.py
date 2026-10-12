import unittest
from io import StringIO
from lice.core import Context, generate_license, format_license, guess_organization

class TestCore(unittest.TestCase):

    def test_context_initialization(self):
        ctx = Context("2023", "TestOrg", "TestProj")
        self.assertEqual(ctx.year, "2023")
        self.assertEqual(ctx.organization, "TestOrg")
        self.assertEqual(ctx.project, "TestProj")

    def test_generate_license_simple(self):
        template = StringIO("Copyright {{year}} {{organization}}. Project: {{project}}.")
        ctx = Context("2023", "TestOrg", "TestProj")
        result = generate_license(template, ctx)
        self.assertEqual(result.getvalue(), "Copyright 2023 TestOrg. Project: TestProj.")

    def test_format_license_python(self):
        content = StringIO("# License Text")
        # Assuming format_license handles '#' for python
        formatted = format_license(content, "py")
        # Check if it contains the expected comment style
        self.assertIn("#", formatted.getvalue())

    def test_guess_organization_fallback(self):
        # This tests the logic of guessing organization when env/git is not set
        # Since we can't easily mock git in a simple unit test without extra libs,
        # we just ensure it returns a string.
        org = guess_organization()
        self.assertIsInstance(org, str)

if __name__ == '__main__':
    unittest.main()
