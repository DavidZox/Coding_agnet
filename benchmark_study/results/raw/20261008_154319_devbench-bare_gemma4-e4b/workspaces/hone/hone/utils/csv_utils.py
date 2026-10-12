import csv
from typing import List, Tuple, Optional

class CSVUtils:
    """
    Utility class for reading and processing CSV files.
    """
    def __init__(self, csv_filepath: str):
        """
        Initializes CSVUtils with the path to the CSV file.

        :param csv_filepath: Path to the CSV file.
        """
        self.filepath: str = csv_filepath

    def get_column_names(self) -> List[str]:
        """
        Reads the header row of the CSV file to extract column names.

        :return: A list of column names.
        :raises FileNotFoundError: If the CSV file is not found.
        """
        try:
            with open(self.filepath, 'r', newline='', encoding='utf-8') as csvfile:
                # Assuming the first row is the header
                reader = csv.reader(csvfile)
                try:
                    header = next(reader)
                    return header
                except StopIteration:
                    return []  # Empty file
        except FileNotFoundError:
            raise FileNotFoundError(f"CSV file not found at path: {self.filepath}")

    def get_data_rows(self) -> List[List[str]]:
        """
        Reads all data rows from the CSV file, excluding the header.

        :return: A list of lists, where each inner list is a data row.
        :raises FileNotFoundError: If the CSV file is not found.
        """
        data_rows: List[List[str]] = []
        try:
            with open(self.filepath, 'r', newline='', encoding='utf-8') as csvfile:
                reader = csv.reader(csvfile)
                
                # Skip the header row
                try:
                    next(reader)
                except StopIteration:
                    return [] # Empty file

                for row in reader:
                    data_rows.append(row)
        except FileNotFoundError:
            raise FileNotFoundError(f"CSV file not found at path: {self.filepath}")
            
        return data_rows
