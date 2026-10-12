import pandas as pd
import os
from typing import List, Dict, Any
# Removed import from progressbar2 here to resolve ModuleNotFoundError at module load time

# Global variable to store the loaded datasets
_datasets: pd.DataFrame = pd.DataFrame()

def load_datasets() -> bool:
    """
    Loads the word vector dataset from datasets.csv into the global _datasets DataFrame.

    Returns:
        bool: True if loading was successful, False otherwise.
    """
    global _datasets
    csv_path = os.path.join(os.path.dirname(__file__), 'datasets.csv')
    
    try:
        # Read the CSV file using pandas
        _datasets = pd.read_csv(csv_path)
        print(f"Successfully loaded {len(_datasets)} datasets from datasets.csv.")
        return True
    except FileNotFoundError:
        print(f"Error: datasets.csv not found at {csv_path}")
        _datasets = pd.DataFrame()
        return False
    except pd.errors.EmptyDataError:
        print(f"Error: datasets.csv is empty.")
        _datasets = pd.DataFrame()
        return False
    except Exception as e:
        print(f"An unexpected error occurred while loading datasets: {e}")
        _datasets = pd.DataFrame()
        return False

def search(lang: str) -> List[Dict[str, Any]]:
    """
    Searches for word vectors matching the specified language.

    Args:
        lang: The language to search for (e.g., 'English', 'Arabic').

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, where each dictionary 
                                represents a matching dataset. Returns an empty list if none found.
    """
    if _datasets.empty:
        print("Datasets not loaded. Please call load_datasets() first.")
        return []
    
    # Exact match search on the 'Language' column
    results_df = _datasets[
        _datasets['Language'] == lang
    ]
    
    # Convert DataFrame rows to list of dictionaries
    results = results_df.to_dict('records')
    return results

def download(number: int = None, name: str = None, save_dir: str = './') -> bool:
    """
    Downloads a specific word vector based on its numerical index or name.

    Args:
        number: The numerical index of the vector to download (1-based). If provided, this takes precedence.
        name: The name of the vector to download. If provided and number is not, this is used for lookup.
        save_dir: The directory where the vector should be saved.

    Returns:
        bool: True if the download process was successful, False otherwise.
    """
    global _datasets
    if _datasets.empty:
        print("Datasets not loaded. Please call load_datasets() first.")
        return False

    target_row = None
    
    # 1. Search by number if provided (Highest Precedence)
    if number is not None:
        try:
            # Convert 1-based index to 0-based index
            index = number - 1
            if 0 <= index < len(_datasets):
                target_row = _datasets.iloc[index]
        except IndexError:
            print(f"Error: Number {number} is out of range.")
            return False

    # 2. Search by name if target_row is still None (i.e., number was not provided or failed)
    if target_row is None and name is not None:
        # Search by name
        name_matches = _datasets[
            _datasets['Name'] == name
        ]
        if not name_matches.empty:
            # If multiple matches, we take the first one as per typical CLI behavior
            target_row = name_matches.iloc[0]
        else:
            print(f"Error: Could not find a target row based on name ({name}).")
            return False
    
    # If target_row is still None, it means neither number nor name provided a valid match
    if target_row is None:
        print("Error: Could not find a target row based on provided parameters (number or name).")
        return False

    # --- Download Logic ---
    # Import requests here to avoid ModuleNotFoundError during module import time
    import requests 
    from progressbar2 import ProgressBar # Import ProgressBar inside the function
    
    url = target_row['URL']
    name_from_data = target_row['Name']
    
    if pd.isna(url) or not url.startswith(('http://', 'https://')):
        print(f"Error: Dataset {name_from_data} has no valid URL to download.")
        return False

    # Ensure save directory exists
    os.makedirs(save_dir, exist_ok=True)
    
    # Create a safe filename from the URL/Name
    # Use the base name from the URL, stripping query parameters
    filename = os.path.basename(url).split('?')[0]
    save_path = os.path.join(save_dir, filename)

    print("-" * 40)
    # Adjust print statement to reflect which parameter was used for identification
    if number is not None and target_row.index == number - 1:
        print(f"Initiating download for: {name_from_data} (Index: {number})")
    elif name is not None:
        print(f"Initiating download for: {name_from_data} (Name: {name})")
    else:
        print(f"Initiating download for: {name_from_data}")
        
    print(f"Source URL: {url}")
    print(f"Saving to: {save_path}")
    
    try:
        # Use requests and progressbar2 for actual download
        response = requests.get(url, stream=True)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

        total_size = int(response.headers.get('content-length', 0))
        block_size = 8192 # 8 KB chunks
        downloaded_size = 0

        with ProgressBar(total=total_size) as pb:
            with open(save_path, 'wb') as f:
                for data in response.iter_content(block_size):
                    f.write(data)
                    downloaded_size += len(data)
                    pb.update(len(data))
        
        print("\nDownload complete.")
        print(f"Successfully downloaded {name_from_data} to {save_dir}")
        print("-" * 40)
        return True

    except requests.exceptions.RequestException as e:
        print(f"\nError during download of {name_from_data}: Network or HTTP error occurred: {e}")
        return False
    except Exception as e:
        print(f"\nAn unexpected error occurred during file saving/download: {e}")
        return False


# Initialization: Attempt to load datasets when the module is imported
# This aligns with the requirement that the data structure must be available.
load_datasets()
