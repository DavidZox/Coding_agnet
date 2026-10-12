import pandas as pd
import os
import requests
from progressbar2 import ProgressBar, Bar, Percentage, ETA
from urllib.parse import urlparse

def load_datasets():
    try:
        file_path = os.path.join(os.path.dirname(__file__), 'datasets.csv')
        datasets_df = pd.read_csv(file_path)
        return datasets_df
    except FileNotFoundError:
        raise FileNotFoundError("The datasets.csv file was not found.")
    except pd.errors.EmptyDataError:
        raise ValueError("The datasets.csv file is empty.")
    except pd.errors.ParserError:
        raise ValueError("Error parsing the datasets.csv file.")

def search(lang):
    datasets_df = load_datasets()
    filtered_df = datasets_df[datasets_df['Language'] == lang]
    return filtered_df.to_dict(orient='records')

def download(number=None, name=None, save_dir='./'):
    datasets_df = load_datasets()
    
    if number is not None:
        dataset = datasets_df[datasets_df.index == number - 1]
    elif name is not None:
        dataset = datasets_df[datasets_df['Name'] == name]
    else:
        raise ValueError("Either number or name must be specified.")
    
    if dataset.empty:
        raise ValueError("No dataset found with the specified number or name.")
    
    url = dataset['URL'].values[0]
    file_name = os.path.basename(urlparse(url).path)
    save_path = os.path.join(save_dir, file_name)
    
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        block_size = 1024  # 1 Kibibyte
        
        widgets = [Percentage(), ' ', Bar(), ' ', ETA()]
        progress_bar = ProgressBar(widgets=widgets, maxval=total_size).start()
        
        with open(save_path, 'wb') as file:
            for data in response.iter_content(block_size):
                progress_bar += len(data)
                file.write(data)
        
        progress_bar.finish()
        print(f"Download completed: {save_path}")
    
    except requests.exceptions.RequestException as e:
        raise ConnectionError(f"Error downloading the file: {e}")
