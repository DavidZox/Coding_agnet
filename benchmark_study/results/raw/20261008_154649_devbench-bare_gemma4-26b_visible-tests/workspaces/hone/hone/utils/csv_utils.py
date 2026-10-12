import csv

class CSVUtils:
    def __init__(self, csv_filepath):
        self.filepath = csv_filepath

    def open_csv(self, mode='r', newline=''):
        return open(self.filepath, mode=mode, newline=newline)

    def get_column_names(self):
        with self.open_csv(mode='r') as f:
            # Using a reader to handle potential complex quoting/delimiters
            # We need to determine the delimiter first or use the default
            # Since Hone class handles delimiters, we'll try to detect or use standard
            # However, for the purpose of this utility, we'll use a basic reader
            # and assume the Hone class will pass the correct context if needed.
            # But based on UML, this class is responsible for the extraction.
            
            # To support custom delimiters, we'd ideally need them passed here.
            # Since the UML doesn't show delimiter in __init__, we'll use a common approach.
            # We'll sniff the delimiter to be robust.
            sample = f.readline()
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample)
            except csv.Error:
                dialect = csv.excel # fallback
            
            reader = csv.reader(f, dialect)
            try:
                return next(reader)
            except StopIteration:
                return []

    def get_data_rows(self):
        with self.open_csv(mode='r') as f:
            sample = f.readline()
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample)
            except csv.Error:
                dialect = csv.excel
            
            reader = csv.reader(f, dialect)
            try:
                next(reader) # skip header
            except StopIteration:
                return []
            
            return [row for row in reader]
