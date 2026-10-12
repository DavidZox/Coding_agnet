import csv

class CSVUtils:
    def __init__(self, csv_filepath):
        self.filepath = csv_filepath

    def get_column_names(self):
        with self.open_csv('r', newline='') as csvfile:
            reader = csv.reader(csvfile, delimiter=',')
            column_names = next(reader)
        return column_names

    def get_data_rows(self):
        with self.open_csv('r', newline='') as csvfile:
            reader = csv.reader(csvfile, delimiter=',')
            next(reader)  # Skip the header row
            data_rows = [row for row in reader]
        return data_rows

    def open_csv(self, mode, newline):
        return open(self.filepath, mode, newline=newline)
