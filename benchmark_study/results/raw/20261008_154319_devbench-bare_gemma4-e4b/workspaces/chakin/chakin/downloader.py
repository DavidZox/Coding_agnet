import pandas as pd
import os
import requests
from tqdm import tqdm
from typing import List, Dict, Union

# Define the path to the datasets file relative to the package structure
DATASETS_FILE = os.path.join(os.path.dirname(__file__), 'datasets.csv')

class Downloader:
    """
    Handles the loading, searching, and downloading of pre-trained word vectors.
    """
    def __init__(self):
        """
        Initializes the Downloader by loading the datasets from datasets.csv.
        """
        self.datasets: pd.DataFrame = self._load_datasets()

    def _load_datasets(self) -> pd.DataFrame:
        """
        Loads the datasets.csv file into a pandas DataFrame.

        Returns:
            pd.DataFrame: DataFrame containing all available word vector metadata.
        """
        try:
            df = pd.read_csv(DATASETS_FILE)
            print(f"Successfully loaded {len(df)} datasets from {DATASETS_FILE}")
            return df
        except FileNotFoundError:
            print(f"Error: Datasets file not found at {DATASETS_FILE}")
            return pd.DataFrame()
        except Exception as e:
            print(f"An error occurred while loading datasets: {e}")
            return pd.DataFrame()

    def search(self, lang: str) -> List[Dict[str, str]]:
        """
        Searches for word vectors matching the specified language.

        Args:
            lang: The language to search for (e.g., 'English', 'Arabic').

        Returns:
            List[Dict[str, str]]: A list of dictionaries, where each dictionary
                                   represents a matching word vector dataset.
        """
        if self.datasets.empty:
            return []

        # Assuming the language column is named 'Language' based on PRD.md structure
        # The example entry suggests the language might be part of the Name field,
        # but the CSV structure implies a dedicated 'Language' column.
        # We will search based on the 'Language' column.
        
        # Case-insensitive search
        results_df = self.datasets[self.datasets['Language'].str.contains(lang, case=False, na=False)]
        
        # Convert DataFrame rows to list of dictionaries
        return results_df.to_dict('records')

    def download(self, number: int = None, name: str = None, save_dir: str = './') -> bool:
        """
        Downloads a specific word vector based on its numerical index or name.

        Args:
            number: The numerical index of the vector to download (1-based).
            name: The exact name of the vector to download.
            save_dir: The directory where the vector file should be saved.

        Returns:
            bool: True if the download was successful, False otherwise.
        """
        if self.datasets.empty:
            print("Error: Datasets not loaded. Cannot perform download.")
            return False

        target_row = None
        
        if number is not None:
            # Number is 1-based index
            try:
                # Check if the number is within the valid range
                if 1 <= number <= len(self.datasets):
                    target_row = self.datasets.iloc[number - 1]
                else:
                    print(f"Error: Number {number} is out of range. Available vectors: 1 to {len(self.datasets)}.")
                    return False
            except IndexError:
                print("Error: Invalid number provided.")
                return False
        elif name is not None:
            # Search by name (exact match on 'Name' column)
            search_results = self.datasets[self.datasets['Name'].str.contains(name, case=False, na=False)]
            if search_results.empty:
                print(f"Error: No dataset found with name matching '{name}'.")
                return False
            # For simplicity, take the first match if multiple exist
            target_row = search_results.iloc[0]
        else:
            print("Error: Must specify either 'number' or 'name' for download.")
            return False

        if target_row is None:
            print("Error: Could not identify the target dataset.")
            return False

        url = target_row['URL']
        vector_name = target_row['Name'].replace('(', '').replace(')', '') # Clean name for filename
        
        # Ensure save directory exists
        os.makedirs(save_dir, exist_ok=True)
        
        # Determine filename from URL or use a derived name
        filename = os.path.basename(url)
        save_path = os.path.join(save_dir, filename)

        print(f"\n--- Starting download for: {vector_name} ---")
        print(f"Source URL: {url}")
        print(f"Saving to: {save_path}")

        try:
            # Stream download to handle large files efficiently
            response = requests.get(url, stream=True)
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

            total_size = int(response.headers.get('content-length', 0))
            block_size = 1024 # 1 Kibibyte

            with open(save_path, 'wb') as f:
                # Use tqdm for progress bar
                with tqdm(total=total_size, unit='B', unit_scale=True, desc=f"Downloading {vector_name}") as pbar:
                    for data in response.iter_content(block_size):
                        f.write(data)
                        pbar.update(len(data))
            
            print(f"\n✅ Successfully downloaded '{vector_name}' to {save_path}")
            return True

        except requests.exceptions.RequestException as e:
            print(f"\n❌ Network or HTTP Error during download: {e}")
            return False
        except Exception as e:
            print(f"\n❌ An unexpected error occurred during download: {e}")
            return False

# Global function interface as per UML_class.md
def load_datasets() -> pd.DataFrame:
    """
    Loads the datasets.csv file. This function is exposed globally.

    Returns:
        pd.DataFrame: DataFrame containing all available word vector metadata.
    """
    downloader = Downloader()
    return downloader.datasets

def search(lang: str) -> List[Dict[str, str]]:
    """
    Searches for word vectors by language.

    Args:
        lang: The language to search for.

    Returns:
        List[Dict[str, str]]: A list of matching word vector datasets.
    """
    downloader = Downloader()
    return downloader.search(lang)

def download(number: int = None, name: str = None, save_dir: str = './') -> bool:
    """
    Downloads a specific word vector by its number or name.

    Args:
        number: The numerical index of the vector to download (1-based).
        name: The exact name of the vector to download.
        save_dir: The directory where the vector file should be saved.

    Returns:
        bool: True if the download was successful, False otherwise.
    """
    downloader = Downloader()
    return downloader.download(number=number, name=name, save_dir=save_dir)
