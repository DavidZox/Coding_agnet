import unittest
from unittest.mock import patch, mock_open
from io import StringIO
from lice.core import main, Context, LICENSES, load_template, generate_license, format_license

class TestLiceCore(unittest.TestCase):

    @patch('sys.argv', ['lice/core.py', 'mit', '-y', '2021', '-o', 'ExampleOrg'])
    @patch('sys.stdout', new_callable=StringIO)
    @patch('lice.core.load_template')
    @patch('lice.core.generate_license')
    @patch('lice.core.format_license')
    def test_main_with_license(self, mock_format_license, mock_generate_license, mock_load_template, mock_stdout):
        mock_template = StringIO("{{year}} {{organization}}")
        mock_load_template.return_value = mock_template
        mock_generate_license.return_value = StringIO("2021 ExampleOrg")
        mock_format_license.return_value = StringIO("# 2021 ExampleOrg")

        main()

        mock_load_template.assert_called_once_with('mit', False)
        mock_generate_license.assert_called_once_with(mock_template, Context('2021', 'ExampleOrg', 'test_core'))
        mock_format_license.assert_called_once_with(StringIO("2021 ExampleOrg"), None)
        self.assertEqual(mock_stdout.getvalue(), "# 2021 ExampleOrg\n")

    @patch('sys.argv', ['lice/core.py', 'mit', '-y', '2021', '-o', 'ExampleOrg', '-l', 'py'])
    @patch('sys.stdout', new_callable=StringIO)
    @patch('lice.core.load_template')
    @patch('lice.core.generate_license')
    @patch('lice.core.format_license')
    def test_main_with_license_and_language(self, mock_format_license, mock_generate_license, mock_load_template, mock_stdout):
        mock_template = StringIO("{{year}} {{organization}}")
        mock_load_template.return_value = mock_template
        mock_generate_license.return_value = StringIO("2021 ExampleOrg")
        mock_format_license.return_value = StringIO("# 2021 ExampleOrg")

        main()

        mock_load_template.assert_called_once_with('mit', False)
        mock_generate_license.assert_called_once_with(mock_template, Context('2021', 'ExampleOrg', 'test_core'))
        mock_format_license.assert_called_once_with(StringIO("2021 ExampleOrg"), 'py')
        self.assertEqual(mock_stdout.getvalue(), "# 2021 ExampleOrg\n")

    @patch('sys.argv', ['lice/core.py', 'mit', '-y', '2021', '-o', 'ExampleOrg', '-f', 'LICENSE'])
    @patch('builtins.open', new_callable=mock_open)
    @patch('lice.core.load_template')
    @patch('lice.core.generate_license')
    @patch('lice.core.format_license')
    def test_main_with_license_and_file(self, mock_format_license, mock_generate_license, mock_load_template, mock_open):
        mock_template = StringIO("{{year}} {{organization}}")
        mock_load_template.return_value = mock_template
        mock_generate_license.return_value = StringIO("2021 ExampleOrg")
        mock_format_license.return_value = StringIO("2021 ExampleOrg")

        main()

        mock_load_template.assert_called_once_with('mit', False)
        mock_generate_license.assert_called_once_with(mock_template, Context('2021', 'ExampleOrg', 'test_core'))
        mock_format_license.assert_called_once_with(StringIO("2021 ExampleOrg"), None)
        mock_open.assert_called_once_with('LICENSE', 'w')
        mock_open().write.assert_called_once_with("2021 ExampleOrg\n")

    @patch('sys.argv', ['lice/core.py', 'mit', '--vars'])
    @patch('sys.stdout', new_callable=StringIO)
    @patch('lice.core.load_template')
    @patch('lice.core.extract_vars')
    def test_main_with_vars(self, mock_extract_vars, mock_load_template, mock_stdout):
        mock_template = StringIO("{{year}} {{organization}}")
        mock_load_template.return_value = mock_template
        mock_extract_vars.return_value = ['year', 'organization']

        main()

        mock_load_template.assert_called_once_with('mit', False)
        mock_extract_vars.assert_called_once_with(mock_template)
        self.assertEqual(mock_stdout.getvalue(), "year\norganization\n")

    @patch('sys.argv', ['lice/core.py', 'mit', '--header'])
    @patch('sys.stdout', new_callable=StringIO)
    @patch('lice.core.load_template')
    @patch('lice.core.generate_license')
    @patch('lice.core.format_license')
    def test_main_with_header(self, mock_format_license, mock_generate_license, mock_load_template, mock_stdout):
        mock_template = StringIO("{{year}} {{organization}}")
        mock_load_template.return_value = mock_template
        mock_generate_license.return_value = StringIO("2021 ExampleOrg")
        mock_format_license.return_value = StringIO("# 2021 ExampleOrg")

        main()

        mock_load_template.assert_called_once_with('mit', True)
        mock_generate_license.assert_called_once_with(mock_template, Context('2021', 'ExampleOrg', 'test_core'))
        mock_format_license.assert_called_once_with(StringIO("2021 ExampleOrg"), None)
        self.assertEqual(mock_stdout.getvalue(), "# 2021 ExampleOrg\n")

if __name__ == '__main__':
    unittest.main()
