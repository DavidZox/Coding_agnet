import pandas as pd
import requests
from progressbar2 import ProgressBar, Bar, Percentage, ETA
import os

def load_datasets():
    return pd.read_csv('chakin/datasets.csv')

def search(lang):
    datasets = load_datasets()
    return datasets[datasets['Language'].str.contains(lang, case=False)]

def download(number=None, name=None, save_dir='./'):
    datasets = load_datasets()
    
    if number is not None:
        dataset = datasets[datasets['Number'] == number]
    elif name is not None:
        dataset = datasets[datasets['Name'] == name]
    else:
        raise ValueError("Either 'number' or 'name' must be provided.")
    
    if dataset.empty:
        raise ValueError("No dataset found with the given number or name.")
    
    url = dataset.iloc[0]['URL']
    file_name = os.path.join(save_dir, url.split('/')[-1])
    
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    
    response = requests.get(url, stream=True)
    response.raise_for_status()
    
    total_size = int(response.headers.get('content-length', 0))
    progress_bar = ProgressBar(max_value=total_size, widgets=[Percentage(), ' ', Bar(), ' ', ETA()])
    progress_bar.start()
    
    with open(file_name, 'wb') as f:
        for data in response.iter_content(chunk_size=1024):
            f.write(data)
            progress_bar.update(f.tell())
    
    progress_bar.finish()
    print(f"Downloaded {file_name}")
