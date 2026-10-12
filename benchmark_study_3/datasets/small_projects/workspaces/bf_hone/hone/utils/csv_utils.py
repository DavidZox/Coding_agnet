"""
Simple helper methods for processing CSV files
"""
from contextlib import contextmanager
import csv
import fileinput

class CSVUtils:

    def __init__(self, csv_filepath):
        self.filepath = csv_filepath

    def get_column_names(self):
        with self.open_csv() as f:
            csvreader = csv.reader(f)
            cols = next(csvreader)
        return cols

    def get_data_rows(self):
        with self.open_csv() as f:
            csvreader = csv.reader(f)
            parsed_csv = list(csvreader)
            data_rows = parsed_csv[1:]
        return data_rows

    @contextmanager
    def open_csv(self, mode='r', newline=''):
        f = fileinput.input(files=self.filepath, openhook=fileinput.hook_encoded(''))
        try:
            yield f
        finally:
            f.close()
