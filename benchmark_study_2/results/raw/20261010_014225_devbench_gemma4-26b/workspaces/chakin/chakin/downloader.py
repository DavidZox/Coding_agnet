import os
import pandas as pd
import urllib.request
import progressbar
from pathlib import Path

def load_datasets():
    """
    Loads the datasets from chakin/datasets.csv.
    Returns a pandas DataFrame.
    """
    csv_path = os.path.join(os.path.dirname(__file__), 'datasets.csv')
    try:
        df = pd.read_csv(csv_path)
        return df
    except FileNotFoundError:
        raise FileNotFoundError(f"The datasets file was not found at {csv_path}")
    except Exception as e:
        raise Exception(f"An error occurred while loading datasets: {e}")

def search(lang: str):
    """
    Searches for word vectors by language.
    Returns a DataFrame containing the matching rows.
    """
    df = load_datasets()
    # Case-insensitive search for language
    result = df[df['Language'].str.contains(lang, case=False, na=False)]
    return result

def download(number: int = None, name: str = None, save_dir: str = './'):
    """
    Downloads a specific word vector by its number (1-indexed) or name.
    """
    df = load_datasets()
    target_row = None

    if number is not None:
        # number is 1-indexed based on user expectation
        if 1 <= number <= len(df):
            target_row = df.iloc[number - 1]
        else:
            raise ValueError(f"Invalid number: {number}. Please provide a number between 1 and {len(df)}.")
    elif name is not None:
        match = df[df['Name'] == name]
        if not match.empty:
            target_row = match.iloc[0]
        else:
            raise ValueError(f"No word vector found with name: {name}")
    else:
        raise ValueError("You must provide either 'number' or 'name' to download.")

    if target_row is None:
        raise ValueError("No valid dataset found for the given parameters.")

    url = target_row['URL']
    file_name = url.split('/')[-1]
    
    # Ensure save_dir exists
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, file_name)

    try:
        print(f"Downloading {target_row['Name']}...")
        
        with urllib.request.urlopen(url) as response, open(save_path, 'wb') as f:
            total_size = int(response.getheader('Content-Length', 0))
            
            with progressbar.ProgressBar(max=total_size) as bar:
                downloaded = 0
                # Increased chunk size to 1MB to optimize download speed in slow network environments
                chunk_size = 1024 * 1024
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    size = f.write(chunk)
                    downloaded += size
                    bar.update(downloaded)
                
        print(f"\nDownload completed: {save_path}")
        return save_path

    except Exception as e:
        if os.path.exists(save_path):
            os.remove(save_path)
        raise Exception(f"An error occurred during download: {e}")
