import pandas as pd
import os
import urllib.request
import sys

def load_datasets():
    """Loads the datasets from the csv file."""
    csv_path = os.path.join(os.path.dirname(__file__), 'datasets.csv')
    return pd.read_csv(csv_path)

def search(lang):
    """
    Search for word vectors by language.
    Returns a list of matching datasets (as dictionaries or strings).
    """
    df = load_datasets()
    # Filter by language (case-insensitive or exact match based on CSV)
    results = df[df['Language'].str.lower() == lang.lower()]
    return results.to_dict(orient='records')

def download(number=None, name=None, save_dir='./'):
    """
    Download a specific word vector by its number or name.
    """
    df = load_datasets()
    target_row = None

    if number is not None:
        # Assuming number is 1-based index for user friendliness
        if 0 < number <= len(df):
            target_row = df.iloc[number - 1]
        else:
            raise ValueError(f"Invalid number: {number}. Must be between 1 and {len(df)}.")
    elif name is not None:
        match = df[df['Name'] == name]
        if not match.empty:
            target_row = match.iloc[0]
        else:
            raise ValueError(f"No dataset found with name: {name}")
    else:
        raise ValueError("Either 'number' or 'name' must be provided.")

    url = target_row['URL']
    file_name = os.path.basename(url)
    save_path = os.path.join(save_dir, file_name)

    # Ensure directory exists
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    # Download with progress bar using urllib (simulated progress bar to avoid progressbar2 dependency)
    try:
        with urllib.request.urlopen(url) as response:
            total_size = int(response.getheader('Content-Length', 0))
            downloaded_size = 0
            
            with open(save_path, 'wb') as f:
                while True:
                    chunk = response.read(1024 * 1024)  # Read in 1MB chunks
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded_size += len(chunk)
                    
                    # Display progress
                    if total_size > 0:
                        percent = (downloaded_size / total_size) * 100
                        sys.stdout.write(f"\rDownloading: {percent:.2f}% ({downloaded_size}/{total_size} bytes)")
                        sys.stdout.flush()
                    else:
                        sys.stdout.write(f"\rDownloading: {downloaded_size} bytes")
                        sys.stdout.flush()
            
            print()  # New line after progress bar
            
    except Exception as e:
        if os.path.exists(save_path):
            os.remove(save_path)
        raise RuntimeError(f"Failed to download file from {url}: {e}")
    
    print(f"Downloaded: {file_name} to {save_dir}")
    return save_path
