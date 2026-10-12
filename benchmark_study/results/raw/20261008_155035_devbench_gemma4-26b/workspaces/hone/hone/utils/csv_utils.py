import csv

class CSVUtils:
    def __init__(self, csv_filepath):
        self.filepath = csv_filepath

    def open_csv(self, mode='r', newline=''):
        """
        Opens the CSV file.
        """
        return open(self.filepath, mode=mode, newline=newline)

    def get_column_names(self, delimiter=','):
        """
        Extracts column names from the CSV file.
        """
        with self.open_csv(mode='r', newline='') as f:
            reader = csv.reader(f, delimiter=delimiter)
            try:
                column_names = next(reader)
                return column_names
            except StopIteration:
                return []

    def get_data_rows(self, delimiter=','):
        """
        Extracts data rows from the CSV file.
        """
        with self.open_csv(mode='r', newline='') as f:
            reader = csv.reader(f, delimiter=delimiter)
            try:
                # Skip the header row
                next(reader)
            except StopIteration:
                return []
            
            data_rows = []
            for row in reader:
                data_rows.append(row)
            return data_rows
