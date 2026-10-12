import csv

class CSVUtils:
    def __init__(self, csv_filepath):
        self.filepath = csv_filepath

    def open_csv(self, mode='r', newline=''):
        """Opens the CSV file with the specified mode and newline character."""
        return open(self.filepath, mode=mode, newline=newline)

    def get_column_names(self, delimiters=None):
        """
        Attempts to parse the column names from the CSV file using provided delimiters.
        If delimiters are not provided, it tries common ones.
        Returns a list of column names.
        """
        if delimiters is None:
            delimiters = [',', ';', '\t', '|']
        
        # Try each delimiter until one successfully parses the first line into multiple columns
        for delimiter in delimiters:
            try:
                with self.open_csv(mode='r', newline='') as f:
                    reader = csv.reader(f, delimiter=delimiter)
                    first_row = next(reader)
                    # A simple heuristic: if we get more than one column, it's likely the correct delimiter
                    # Or if the file is empty, return empty list
                    if first_row:
                        return [col.strip() for col in first_row]
            except (StopIteration, csv.Error):
                continue
        
        return []

    def get_data_rows(self, delimiters=None):
        """
        Extracts all data rows from the CSV file.
        Uses the same delimiter logic as get_column_names to find the first valid row.
        Returns a list of lists, where each inner list is a row of data.
        """
        if delimiters is None:
            delimiters = [',', ';', '\t', '|']

        for delimiter in delimiters:
            try:
                with self.open_csv(mode='r', newline='') as f:
                    reader = csv.reader(f, delimiter=delimiter)
                    try:
                        header = next(reader)
                        # If we successfully read a header, the rest are data rows
                        rows = [row for row in reader]
                        return rows
                    except StopIteration:
                        # File is empty
                        return []
            except (csv.Error):
                continue
        
        return []
