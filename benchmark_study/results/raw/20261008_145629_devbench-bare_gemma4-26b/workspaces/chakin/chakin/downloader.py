import os
import pandas as pd
import requests
from progressbar2 import ProgressBar

class Downloader:
    def __init__(self, csv_path='chakin/datasets.csv'):
        self.csv_path = csv_path
        self.datasets = self.load_datasets()

    def load_datasets(self):
        """
        Loads the datasets from the CSV file.
        """
        try:
            return pd.read_csv(self.csv_path)
        except Exception as e:
            raise FileNotFoundError(f"Could not load datasets at {self.csv_path}: {e}")

    def search(self, lang):
        """
        Search for word vectors by language.
        Returns a list of datasets matching the language.
        """
        results = self.datasets[self.datasets['Language'].str.contains(lang, case=False, na=False)]
        return results.to_dict('records')

    def download(self, number=None, name=None, save_dir='./'):
        """
        Download a specific word vector by its number or name.
        """
        if number is not None:
            # Assuming 'number' refers to the 1-based index in the CSV
            target_row = self.datasets.iloc[number - 1]
        elif name is not None:
            target_row = self.datasets[self.datasets['Name'] == name]
            if target_row.empty:
                raise ValueError(f"No dataset found with name: {name}")
            target_row = target_row.iloc[0]
        else:
            raise ValueError("Must provide either 'number' or 'name'")

        url = target_row['URL']
        file_name = url.split('/')[-1]
        save_path = os.path.join(save_dir, file_name)

        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))

        with open(save_path, 'wb') as f, ProgressBar(maxval=total_size) as bar:
            for data in response.iter_content(chunk_size=1024):
                size = f.write(data)
                f.flush()
                bar.update(size)
        
        return save_path

def load_datasets():
    """Global function to load datasets."""
    return Downloader().datasets

def search(lang):
    """Global function to search by language."""
    return Downloader().search(lang)

def download(number=None, name=None, save_dir='./'):
    """Global function to download by number or name."""
    return Downloader().download(number=number, name=name, save_dir=save_dir)
