import unittest
from readtime.api import of_text


class BaseTestCase(unittest.TestCase):
    def test_custom_wpm(self):
        """
        Test case for custom wpm.
        """
        text = 'some test content ' * 100
        result = of_text(text)
        self.assertEqual(result.wpm, 265)
        self.assertEqual(result.seconds, 68)
        self.assertEqual(result.text, '2 min')
        wpm = 50
        result = of_text(text, wpm=wpm)
        self.assertEqual(result.wpm, wpm)
        self.assertEqual(result.seconds, 360)
        self.assertEqual(type(result.seconds), int)
        self.assertEqual(result.text, '6 min')
        self.assertEqual(str(result), '6 min read')
