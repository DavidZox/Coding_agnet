# -*- coding: utf-8 -*-
import os

import pandas as pd


def load_datasets(path=os.path.join(os.path.dirname(__file__), 'datasets.csv')):
    datasets = pd.read_csv(path)
    return datasets


def search(lang=''):
    """Search pre-trained word vectors by their language
    :param lang: str, default ''
    :return: None
        print search result as pandas DataFrame
    """
    df = load_datasets()
    if lang == '':
        print(df[['Name', 'Dimension', 'Corpus', 'VocabularySize', 'Method', 'Language', 'Author']])
    else:
        rows = df[df.Language==lang]
        print(rows[['Name', 'Dimension', 'Corpus', 'VocabularySize', 'Method', 'Language', 'Author']])
