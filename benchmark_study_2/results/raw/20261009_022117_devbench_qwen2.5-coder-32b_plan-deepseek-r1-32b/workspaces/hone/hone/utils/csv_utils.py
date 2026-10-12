import csv
from contextlib import contextmanager
from hone.utils.global_functions import Global_functions

class CSVUtils(Global_functions):
    def __init__(self, csv_filepath):
        self.filepath = csv_filepath

    @contextmanager
    def open_csv(self, mode, newline):
        with open(self.filepath, mode, newline=newline) as file:
            yield csv.reader(file)

    def get_column_names(self):
        with self.open_csv('r', newline='') as reader:
            return next(reader)

    def get_data_rows(self):
        with self.open_csv('r', newline='') as reader:
            next(reader)  # Skip the header row
            return list(reader)
