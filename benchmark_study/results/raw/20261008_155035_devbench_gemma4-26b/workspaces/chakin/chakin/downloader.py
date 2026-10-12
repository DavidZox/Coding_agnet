import os
import pandas as pd
import urllib.request

def load_datasets():
    """
    Loads the datasets from the chakin/datasets.csv file.
    Returns a pandas DataFrame.
    """
    csv_path = os.path.join(os.path.dirname(__file__), 'datasets.csv')
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Dataset file not found at {csv_path}")
    
    # The format is Name,Dimension,Corpus,VocabularySize,Method,Language,Paper,Author,URL
    try:
        df = pd.read_csv(csv_path)
        return df
    except Exception as e:
        raise Exception(f"Error loading datasets: {e}")

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
    Downloads a specific word vector by its number (index) or name.
    Uses text-based progress display.
    """
    df = load_datasets()
    target_row = None

    if number is not None:
        # Using 1-based indexing for user-friendly 'number' if intended, 
        # but standard practice in these tasks is often 0-based or direct index.
        # Given the example 'number=2', we'll treat it as the index in the dataframe.
        try:
            if 0 <= number < len(df):
                target_row = df.iloc[number]
            else:
                raise IndexError(f"Index {number} is out of bounds.")
        except IndexError as e:
            print(f"Error: {e}")
            return
    elif name is not None:
        try:
            match = df[df['Name'] == name]
            if not match.empty:
                target_row = match.iloc[0]
            else:
                print(f"Error: No dataset found with name '{name}'")
                return
        except Exception as e:
            print(f"Error searching by name: {e}")
            return
    else:
        print("Error: You must provide either 'number' or 'name'.")
        return

    if target_row is None:
        return

    url = target_row['URL']
    file_name = url.split('/')[-1]
    
    # Ensure save_dir exists
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    
    save_path = os.path.join(save_dir, file_name)

    try:
        print(f"Downloading {target_row['Name']}...")
        
        # Using urllib.request to download
        with urllib.request.urlopen(url) as response:
            total_size = int(response.getheader('Content-Length', 0))
            
            with open(save_path, 'wb') as f:
                downloaded = 0
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        print(f"\rProgress: {percent:.2f}% ({downloaded}/{total_size} bytes)", end="")
                    else:
                        print(f"\rDownloaded: {downloaded} bytes", end="")
        
        print(f"\nDownload completed: {save_path}")

    except Exception as e:
        print(f"\nAn error occurred during download: {e}")
