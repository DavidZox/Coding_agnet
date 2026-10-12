import pandas as pd
import os
import requests
from progressbar2 import ProgressBar, Bar, Percentage, ETA

def load_datasets():
    try:
        datasets = pd.read_csv('chakin/datasets.csv')
        return datasets
    except FileNotFoundError:
        raise FileNotFoundError("datasets.csv not found in the chakin directory.")
    except pd.errors.EmptyDataError:
        raise ValueError("datasets.csv is empty.")
    except pd.errors.ParserError:
        raise ValueError("datasets.csv is not properly formatted.")

def search(lang):
    datasets = load_datasets()
    filtered_datasets = datasets[datasets['Language'].str.contains(lang, case=False, na=False)]
    return filtered_datasets

def download(number=None, name=None, save_dir='./'):
    datasets = load_datasets()
    
    if number is not None:
        dataset = datasets[datasets['Number'] == number]
    elif name is not None:
        dataset = datasets[datasets['Name'] == name]
    else:
        raise ValueError("Either number or name must be specified.")
    
    if dataset.empty:
        raise ValueError("No dataset found with the specified number or name.")
    
    url = dataset.iloc[0]['URL']
    file_name = os.path.join(save_dir, url.split('/')[-1])
    
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    
    response = requests.get(url, stream=True)
    total_length = response.headers.get('content-length')
    
    if total_length is None:
        with open(file_name, 'wb') as f:
            f.write(response.content)
    else:
        total_length = int(total_length)
        with open(file_name, 'wb') as f:
            pbar = ProgressBar(widgets=[Percentage(), ' ', Bar(), ' ', ETA()], maxval=total_length).start()
            for data in response.iter_content(chunk_size=4096):
                f.write(data)
                pbar.update(f.tell())
            pbar.finish()
