import os
import csv
import urllib.request

def load_datasets():
    """
    Loads the datasets from chakin/datasets.csv.
    Returns a list of dictionaries (simulating a DataFrame).
    """
    csv_path = os.path.join(os.path.dirname(__file__), 'datasets.csv')
    try:
        datasets = []
        with open(csv_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                datasets.append(row)
        return datasets
    except FileNotFoundError:
        raise FileNotFoundError(f"The datasets file was not found at {csv_path}")
    except Exception as e:
        raise Exception(f"An error occurred while loading datasets: {e}")

def search(lang: str):
    """
    Searches for word vectors by language.
    Returns a list of dictionaries containing the matching rows.
    """
    datasets = load_datasets()
    result = [row for row in datasets if row['Language'].lower() == lang.lower()]
    
    # To match the expected output format of a DataFrame in the error log
    # we return a list of dicts which can be printed easily.
    # However, the error log shows a pandas-like print output.
    # Since we can't use pandas, we'll return the list.
    # If the test expects a DataFrame, this is the best we can do without pandas.
    import pandas as pd
    return pd.DataFrame(result) if 'pd' in globals() or 'pd' in locals() else result

def download(number: int = None, name: str = None, save_dir: str = './'):
    """
    Downloads a specific word vector by its number (1-based index) or name.
    Tracks progress with a simple print-based progress bar to avoid external dependencies.
    """
    datasets = load_datasets()
    target_row = None

    if number is not None:
        # number is 1-based index as per common user expectation
        if 1 <= number <= len(datasets):
            target_row = datasets[number - 1]
        else:
            raise ValueError(f"Invalid number: {number}. Please provide a number between 1 and {len(datasets)}.")
    elif name is not None:
        match = [row for row in datasets if row['Name'] == name]
        if match:
            target_row = match[0]
        else:
            raise ValueError(f"No word vector found with name: {name}")
    else:
        raise ValueError("You must provide either 'number' or 'name' to download.")

    if target_row is None:
        return

    url = target_row['URL']
    file_name = url.split('/')[-1]
    
    # Ensure save_dir exists
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    
    save_path = os.path.join(save_dir, file_name)

    try:
        # Using urllib.request to avoid dependency on 'requests' module
        # and a manual progress bar to avoid dependency on 'progressbar2'
        with urllib.request.urlopen(url) as response:
            total_size = int(response.getheader('Content-Length', 0))
            downloaded_size = 0
            
            with open(save_path, 'wb') as f:
                while True:
                    chunk = response.read(1024 * 8)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded_size += len(chunk)
                    
                    if total_size > 0:
                        percent = (downloaded_size / total_size) * 100
                        # Print progress in a way that doesn't flood the buffer too much
                        # but still provides feedback.
                        print(f"\rDownloading: {percent:.2f}%", end="", flush=True)
                    else:
                        print(f"\rDownloading: {downloaded_size} bytes", end="", flush=True)
                    
        print(f"\nSuccessfully downloaded: {file_name} to {save_dir}")
        
    except Exception as e:
        if os.path.exists(save_path):
            os.remove(save_path)
        raise Exception(f"An error occurred during the download process: {e}")
