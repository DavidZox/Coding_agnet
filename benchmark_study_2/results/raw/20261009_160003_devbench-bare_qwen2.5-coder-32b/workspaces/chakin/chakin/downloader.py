import os
import pandas as pd
import requests
from progressbar import progressbar

def load_datasets():
    """Load the datasets from the CSV file."""
    csv_path = os.path.join(os.path.dirname(__file__), 'datasets.csv')
    return pd.read_csv(csv_path)

def search(lang):
    """
    Search for word vectors by language.

    Parameters:
    lang (str): The language to search for.

    Returns:
    pd.DataFrame: A DataFrame containing the search results.
    """
    datasets = load_datasets()
    return datasets[datasets['Language'].str.contains(lang, case=False, na=False)]

def download(number=None, name=None, save_dir='./'):
    """
    Download a specific word vector by its number or name.

    Parameters:
    number (int): The number of the word vector to download.
    name (str): The name of the word vector to download.
    save_dir (str): The directory to save the downloaded word vector.

    Returns:
    str: The path to the downloaded word vector file.
    """
    if not (number or name):
        raise ValueError("Either 'number' or 'name' must be provided.")

    datasets = load_datasets()
    if number is not None:
        dataset = datasets[datasets['Number'] == number]
    else:
        dataset = datasets[datasets['Name'] == name]

    if dataset.empty:
        raise ValueError("No dataset found with the given number or name.")

    url = dataset.iloc[0]['URL']
    file_name = os.path.basename(url)
    save_path = os.path.join(save_dir, file_name)

    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    response = requests.get(url, stream=True)
    response.raise_for_status()

    total_size = int(response.headers.get('content-length', 0))
    with open(save_path, 'wb') as f, progressbar(range(total_size), redirect_stdout=True) as bar:
        for data in response.iter_content(1024):
            f.write(data)
            bar.update(len(data))

    return save_path
