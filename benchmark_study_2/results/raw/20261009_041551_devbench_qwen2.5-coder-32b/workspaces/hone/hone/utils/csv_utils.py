import csv

class CSVUtils:
    def __init__(self, csv_filepath):
        self.filepath = csv_filepath

    def get_column_names(self):
        with self.open_csv('r', newline='') as csvfile:
            reader = csv.reader(csvfile)
            column_names = next(reader)
        return column_names

    def get_data_rows(self):
        data_rows = []
        with self.open_csv('r', newline='') as csvfile:
            reader = csv.reader(csvfile)
            next(reader)  # Skip the header row
            for row in reader:
                data_rows.append(row)
        return data_rows

    def open_csv(self, mode, newline):
        return open(self.filepath, mode, newline=newline)
