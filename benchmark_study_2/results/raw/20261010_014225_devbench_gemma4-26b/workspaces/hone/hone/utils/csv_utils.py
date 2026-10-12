import csv

class CSVUtils:
    def __init__(self, csv_filepath):
        self.filepath = csv_filepath

    def open_csv(self, mode='r', newline=''):
        """Opens the CSV file with the specified mode and newline character."""
        return open(self.filepath, mode=mode, newline=newline)

    def get_column_names(self, delimiter=','):
        """Extracts the column names from the first row of the CSV file."""
        with self.open_csv(mode='r') as f:
            reader = csv.reader(f, delimiter=delimiter)
            try:
                column_names = next(reader)
                return column_names
            except StopIteration:
                return []

    def get_data_rows(self, delimiter=','):
        """Extracts all data rows from the CSV file, skipping the header."""
        with self.open_csv(mode='r') as f:
            reader = csv.reader(f, delimiter=delimiter)
            try:
                next(reader)  # Skip header
            except StopIteration:
                return []
            
            data_rows = [row for row in reader]
            return data_rows
