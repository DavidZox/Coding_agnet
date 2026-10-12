import pandas as pd
import os
import requests
from progressbar import progressbar
from requests.exceptions import RequestException

def load_datasets():
    datasets_path = os.path.join(os.path.dirname(__file__), 'datasets.csv')
    return pd.read_csv(datasets_path)

def search(lang):
    datasets = load_datasets()
    filtered_datasets = datasets[datasets['Language'].str.contains(lang, case=False, na=False)]
    if filtered_datasets.empty:
        return "No word vectors found for the specified language."
    return filtered_datasets.to_string(index=False)

def download(number=None, name=None, save_dir='./'):
    datasets = load_datasets()
    
    if number is not None:
        dataset = datasets[datasets['Number'] == number]
    elif name is not None:
        dataset = datasets[datasets['Name'] == name]
    else:
        raise ValueError("Either 'number' or 'name' must be specified.")
    
    if dataset.empty:
        raise ValueError("No dataset found with the specified number or name.")
    
    url = dataset.iloc[0]['URL']
    file_name = os.path.join(save_dir, url.split('/')[-1])
    
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        total_size = int(response.headers.get('content-length', 0))
        
        with open(file_name, 'wb') as f:
            for data in progressbar(response.iter_content(1024), max_value=total_size // 1024):
                f.write(data)
    
    except RequestException as e:
        raise Exception(f"Network error occurred: {e}")
    except IOError as e:
        raise Exception(f"File saving error occurred: {e}")
    
    return file_name
