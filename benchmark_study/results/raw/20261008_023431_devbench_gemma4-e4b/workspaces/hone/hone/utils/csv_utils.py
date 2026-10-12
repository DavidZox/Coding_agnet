import csv
from typing import List, Optional

class CSVUtils:
    """
    Utility class for reading and processing CSV files.
    """
    def __init__(self, csv_filepath: str, delimiter: str = ','):
        """
        Initializes CSVUtils with the path to the CSV file and the delimiter.

        Args:
            csv_filepath: Path to the input CSV file.
            delimiter: The delimiter used in the CSV file (default is ',').
        """
        self.filepath = csv_filepath
        self.delimiter = delimiter

    def get_column_names(self) -> List[str]:
        """
        Reads the first row of the CSV file to extract column names.

        Returns:
            A list of strings representing the column names.
        
        Raises:
            FileNotFoundError: If the CSV file does not exist.
        """
        try:
            with open(self.filepath, mode='r', newline='', encoding='utf-8') as csvfile:
                reader = csv.reader(csvfile, delimiter=self.delimiter)
                try:
                    # Read the first row (header)
                    header = next(reader)
                    return header
                except StopIteration:
                    # Handle empty file
                    return []
        except FileNotFoundError:
            raise FileNotFoundError(f"The file was not found at: {self.filepath}")

    def get_data_rows(self) -> List[List[str]]:
        """
        Reads all data rows from the CSV file, excluding the header.

        Returns:
            A list of lists, where each inner list is a data row.
        
        Raises:
            FileNotFoundError: If the CSV file does not exist.
        """
        data_rows: List[List[str]] = []
        try:
            with open(self.filepath, mode='r', newline='', encoding='utf-8') as csvfile:
                reader = csv.reader(csvfile, delimiter=self.delimiter)
                
                # Skip the header row
                try:
                    next(reader)
                except StopIteration:
                    # File is empty
                    return []
                
                # Read all remaining rows
                for row in reader:
                    data_rows.append(row)
            return data_rows
        except FileNotFoundError:
            raise FileNotFoundError(f"The file was not found at: {self.filepath}")
