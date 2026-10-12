import csv
from contextlib import contextmanager

class CSVUtils:
    def __init__(self, csv_filepath):
        self.filepath = csv_filepath

    @contextmanager
    def open_csv(self, mode='r', newline=''):
        """Context manager to open a CSV file."""
        f = open(self.filepath, mode=mode, newline=newline)
        try:
            yield f
        finally:
            f.close()

    def get_column_names(self, delimiter=','):
        """Extracts column names from the CSV file."""
        with self.open_csv(mode='r', newline='') as f:
            reader = csv.reader(f, delimiter=delimiter)
            try:
                column_names = next(reader)
                return column_names
            except StopIteration:
                return []

    def get_data_rows(self, delimiter=','):
        """Extracts data rows from the CSV file."""
        with self.open_csv(mode='r', newline='') as f:
            reader = csv.reader(f, delimiter=delimiter)
            # Skip header
            try:
                next(reader)
            except StopIteration:
                return []
            
            data_rows = []
            for row in reader:
                data_rows.append(row)
            return data_rows
