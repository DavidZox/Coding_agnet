import csv
from typing import List, Any

class CSVUtils:
    """
    Utility class for reading and processing CSV files.
    """
    def __init__(self, csv_filepath: str, delimiter: str = ','):
        """
        Initializes CSVUtils with the CSV file path and delimiter.

        Args:
            csv_filepath: Path to the input CSV file.
            delimiter: The character used to separate fields in the CSV.
        """
        self.filepath = csv_filepath
        self.delimiter = delimiter

    def get_column_names(self) -> List[str]:
        """
        Reads the first row of the CSV file to extract column names.

        Returns:
            A list of strings representing the column headers.
        """
        try:
            with open(self.filepath, mode='r', newline='', encoding='utf-8') as csvfile:
                reader = csv.reader(csvfile, delimiter=self.delimiter)
                try:
                    # Read the first row (column names)
                    column_names = next(reader)
                    return column_names
                except StopIteration:
                    # Handle empty file
                    return []
        except FileNotFoundError:
            raise FileNotFoundError(f"Error: CSV file not found at {self.filepath}")
        except Exception as e:
            raise IOError(f"Error reading column names from {self.filepath}: {e}")

    def get_data_rows(self) -> List[List[str]]:
        """
        Reads all data rows from the CSV file, excluding the header row.

        Returns:
            A list of lists, where each inner list is a data row.
        """
        data_rows = []
        try:
            with open(self.filepath, mode='r', newline='', encoding='utf-8') as csvfile:
                reader = csv.reader(csvfile, delimiter=self.delimiter)
                
                # Skip the header row
                try:
                    next(reader)
                except StopIteration:
                    # File is empty or only has a header (which we skipped)
                    return []

                # Read all remaining rows
                for row in reader:
                    data_rows.append(row)
            return data_rows
        except FileNotFoundError:
            raise FileNotFoundError(f"Error: CSV file not found at {self.filepath}")
        except Exception as e:
            raise IOError(f"Error reading data rows from {self.filepath}: {e}")
