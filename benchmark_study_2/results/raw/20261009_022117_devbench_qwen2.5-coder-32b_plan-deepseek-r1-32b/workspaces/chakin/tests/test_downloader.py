import unittest
from unittest.mock import patch, mock_open
import pandas as pd
from chakin.downloader import search, load_datasets

class TestDownloader(unittest.TestCase):

    @patch('chakin.downloader.load_datasets')
    def test_search_by_language(self, mock_load_datasets):
        mock_data = pd.DataFrame({
            'Name': ['fastText(ar)', 'fastText(de)', 'fastText(en)'],
            'Dimension': [300, 300, 300],
            'Corpus': ['Wikipedia', 'Wikipedia', 'Wikipedia'],
            'VocabularySize': ['610K', '2.3M', '2.9M'],
            'Method': ['fastText', 'fastText', 'fastText'],
            'Language': ['Arabic', 'German', 'English'],
            'Paper': ['Enriching Word Vectors with Subword Information', 'Enriching Word Vectors with Subword Information', 'Enriching Word Vectors with Subword Information'],
            'Author': ['Facebook', 'Facebook', 'Facebook'],
            'URL': ['https://dl.fbaipublicfiles.com/fasttext/vectors-crawl/cc.ar.300.vec.gz', 'https://dl.fbaipublicfiles.com/fasttext/vectors-crawl/cc.de.300.vec.gz', 'https://dl.fbaipublicfiles.com/fasttext/vectors-crawl/cc.en.300.vec.gz']
        })
        mock_load_datasets.return_value = mock_data

        result = search(lang='English')
        expected_output = "Name   Dimension     Corpus VocabularySize    Method Language                           Paper    Author                                               URL\nfastText(en)  300  Wikipedia         2.9M  fastText  English  Enriching Word Vectors with Subword Information  Facebook  https://dl.fbaipublicfiles.com/fasttext/vectors-crawl/cc.en.300.vec.gz"
        self.assertEqual(result, expected_output)

    @patch('chakin.downloader.load_datasets')
    def test_search_no_results(self, mock_load_datasets):
        mock_data = pd.DataFrame({
            'Name': ['fastText(ar)', 'fastText(de)'],
            'Dimension': [300, 300],
            'Corpus': ['Wikipedia', 'Wikipedia'],
            'VocabularySize': ['610K', '2.3M'],
            'Method': ['fastText', 'fastText'],
            'Language': ['Arabic', 'German'],
            'Paper': ['Enriching Word Vectors with Subword Information', 'Enriching Word Vectors with Subword Information'],
            'Author': ['Facebook', 'Facebook'],
            'URL': ['https://dl.fbaipublicfiles.com/fasttext/vectors-crawl/cc.ar.300.vec.gz', 'https://dl.fbaipublicfiles.com/fasttext/vectors-crawl/cc.de.300.vec.gz']
        })
        mock_load_datasets.return_value = mock_data

        result = search(lang='Spanish')
        self.assertEqual(result, "No word vectors found for the specified language.")

if __name__ == '__main__':
    unittest.main()
