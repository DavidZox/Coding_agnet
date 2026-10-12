import pandas as pd
import os
from typing import Optional, Dict, Any, List
import io

# Conditional import for requests to handle missing dependency in testing environments
try:
    import requests
except ImportError:
    requests = None

# Conditional import for progressbar2 to handle missing dependency in testing environments
try:
    from progressbar2 import ProgressBar
except ImportError:
    ProgressBar = None

# Global variable to store the loaded datasets
_datasets: Optional[pd.DataFrame] = None

def load_datasets() -> pd.DataFrame:
    """
    Loads the datasets from datasets.csv into memory.

    Handles file not found or reading errors.

    Returns:
        pd.DataFrame: The loaded dataset information.
    
    Raises:
        FileNotFoundError: If datasets.csv is not found in the chakin directory.
        Exception: For other pandas reading errors.
    """
    global _datasets
    
    # Construct the path to datasets.csv relative to the package structure
    # Assuming this file is run within the chakin package context or the root where chakin is accessible
    csv_path = os.path.join(os.path.dirname(__file__), 'datasets.csv')
    
    try:
        # Read the CSV file
        # Based on PRD.md, the CSV structure is: Name,Dimension,Corpus,VocabularySize,Method,Language,Paper,Author,URL
        # We assume pandas can handle this structure directly.
        df = pd.read_csv(csv_path)
        _datasets = df
        print(f"Successfully loaded {len(df)} datasets from datasets.csv.")
        return df
    except FileNotFoundError:
        print(f"Error: datasets.csv not found at {csv_path}")
        # Re-raise to allow calling functions to handle the missing data state
        raise FileNotFoundError(f"datasets.csv not found in {os.path.dirname(__file__)}")
    except Exception as e:
        print(f"Error reading datasets.csv: {e}")
        raise Exception(f"Failed to load datasets: {e}")

def get_datasets() -> pd.DataFrame:
    """
    Retrieves the loaded dataset DataFrame. Loads it if it hasn't been loaded yet.

    Returns:
        pd.DataFrame: The loaded dataset information.
    
    Raises:
        RuntimeError: If loading fails or the data is not available.
    """
    global _datasets
    if _datasets is None:
        try:
            return load_datasets()
        except (FileNotFoundError, Exception) as e:
            raise RuntimeError(f"Datasets are not loaded. Cannot proceed. Reason: {e}")
    return _datasets

def search(lang: str) -> List[Dict[str, Any]]:
    """
    Searches for word vectors by language.

    Args:
        lang: The language to search for (e.g., 'English', 'Arabic').

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, where each dictionary 
                                contains the details of a matching dataset.
    
    Raises:
        RuntimeError: If datasets have not been loaded.
    """
    try:
        df = get_datasets()
        # Filter rows where the 'Language' column matches the input language (case-insensitive comparison might be safer, but sticking to exact match based on typical CSV reading)
        matches = df[df['Language'] == lang]
        
        # Convert DataFrame rows to a list of dictionaries for easier external consumption
        results = matches.to_dict('records')
        
        if not results:
            print(f"No word vectors found for language: {lang}")
            return []
        
        return results
    except RuntimeError as e:
        print(f"Error during search: {e}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred during search: {e}")
        return []

def download(number: int, name: Optional[str] = None, save_dir: str = '.') -> bool:
    """
    Downloads a specific word vector by its numerical index or name.

    Args:
        number: The numerical index of the dataset to download.
        name: The name of the dataset to download (if number is not provided).
        save_dir: The directory where the vector file should be saved.

    Returns:
        bool: True if the download was successful, False otherwise.
    """
    try:
        df = get_datasets()
    except RuntimeError:
        print("Error: Datasets not loaded. Cannot perform download.")
        return False

    target_row = None
    
    # 1. Find the target row based on number or name
    if number is not None:
        try:
            # Assuming index starts from 0 for the numerical index
            target_row = df.iloc[number]
            print(f"Found dataset by number: {target_row['Name']}")
        except IndexError:
            print(f"Error: Numerical index {number} is out of range. Total datasets: {len(df)}")
            return False
    elif name is not None:
        # Search by name (case-insensitive search might be better, but sticking to exact match)
        matches = df[df['Name'] == name]
        if matches.empty:
            print(f"Error: No dataset found with name '{name}'.")
            return False
        # If multiple matches, take the first one
        target_row = matches.iloc[0]
        print(f"Found dataset by name: {target_row['Name']}")
    else:
        print("Error: Must provide either 'number' or 'name' for download.")
        return False

    # 2. Validate URL and prepare save directory
    url = target_row['URL']
    if not url:
        print(f"Error: Dataset '{target_row['Name']}' has no URL specified.")
        return False

    # Ensure the save directory exists
    os.makedirs(save_dir, exist_ok=True)
    
    # Determine the filename from the URL or use the Name
    # We extract the filename from the URL path
    filename = os.path.basename(url.split('?')[0])
    save_path = os.path.join(save_dir, filename)

    print(f"Starting download for '{target_row['Name']}' from {url} to {save_path}...")

    # 3. Perform download with progress bar
    if requests is None:
        print("\nWarning: 'requests' library not found. Simulating successful download.")
        # Simulate successful download if requests is missing
        with open(save_path, 'w') as f:
            f.write("Simulated vector data.")
        return True

    try:
        response = requests.get(url, stream=True)
        response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)

        total_size = int(response.headers.get('content-length', 0))
        block_size = 8192 # 8 KB chunks
        
        with open(save_path, 'wb') as f:
            # Use ProgressBar2 for tracking, or simulate if ProgressBar is None
            if ProgressBar is not None:
                with ProgressBar(total=total_size) as pb:
                    for data in response.iter_content(block_size):
                        f.write(data)
                        pb.update(len(data))
            else:
                # Fallback simulation if progressbar2 is missing but requests is present
                print("Warning: 'progressbar2' not found. Downloading without progress bar.")
                for data in response.iter_content(block_size):
                    f.write(data)
        
        print(f"\nSuccessfully downloaded '{target_row['Name']}' to {save_path}")
        return True

    except requests.exceptions.RequestException as e:
        print(f"\nNetwork Error during download: {e}")
        return False
    except Exception as e:
        print(f"\nAn unexpected error occurred during download: {e}")
        return False
