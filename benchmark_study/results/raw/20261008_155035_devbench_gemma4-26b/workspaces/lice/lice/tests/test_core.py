import unittest
from lice.core import Context

class TestContext(unittest.TestCase):
    def test_context_initialization(self):
        """測試 Context 類別是否能正常實例化並正確賦值"""
        year = "2023"
        organization = "TestOrg"
        project = "TestProject"
        
        context = Context(year, organization, project)
        
        self.assertEqual(context.year, year)
        self.assertEqual(context.organization, organization)
        self.assertEqual(context.project, project)

if __name__ == '__main__':
    unittest.main()
