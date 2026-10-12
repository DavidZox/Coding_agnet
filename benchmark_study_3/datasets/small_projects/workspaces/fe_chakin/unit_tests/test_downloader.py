import os
import unittest
from unittest.mock import patch, MagicMock

from chakin.downloader import load_datasets

class TestDownloader(unittest.TestCase):

    name = 'word2vec.Wiki-NEologd.50d'
    number = 22

    def test_load_datasets(self):
        df = load_datasets()
        for column in ['Name', 'Dimension', 'Corpus', 'VocabularySize', 'Method', 'Language', 'Author', 'URL']:
            self.assertIn(column, df.columns)
        self.assertEqual(df.iloc[self.number]['Name'], self.name)


if __name__ == '__main__':
    unittest.main()
