import csv

class CSVUtils:
    def __init__(self, csv_filepath):
        self.filepath = csv_filepath

    def open_csv(self, mode='r', newline=''):
        return open(self.filepath, mode=mode, newline=newline)

    def get_column_names(self):
        """
        Reads the CSV file and extracts the column names from the first row.
        """
        with self.open_csv(mode='r') as f:
            # Using a basic reader to get the first line as headers
            reader = csv.reader(f)
            try:
                column_names = next(reader)
                return column_names
            except StopIteration:
                return []

    def get_data_rows(self):
        """
        Reads the CSV file and extracts all data rows.
        """
        with self.open_csv(mode='r') as f:
            reader = csv.reader(f)
            try:
                next(reader)  # Skip header row
                return [row for row in reader]
            except StopIteration:
                return []
