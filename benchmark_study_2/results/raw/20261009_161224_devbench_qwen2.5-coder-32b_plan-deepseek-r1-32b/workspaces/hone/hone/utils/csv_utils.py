import csv
from contextlib import contextmanager

class CSVUtils:
    def __init__(self, csv_filepath, delimiters=None):
        self.filepath = csv_filepath
        self.delimiters = delimiters if delimiters is not None else [',']

    @contextmanager
    def open_csv(self, mode='r', newline=''):
        with open(self.filepath, mode, newline=newline) as file:
            yield file

    def get_column_names(self, delimiter=','):
        with self.open_csv() as file:
            reader = csv.reader(file, delimiter=delimiter)
            column_names = next(reader)
        return column_names

    def get_data_rows(self, delimiter=','):
        with self.open_csv() as file:
            reader = csv.reader(file, delimiter=delimiter)
            next(reader)  # Skip the header row
            data_rows = [row for row in reader]
        return data_rows
