import csv

class CSVUtils:
    def __init__(self, csv_filepath, delimiter=','):
        self.filepath = csv_filepath
        self.delimiter = delimiter

    def open_csv(self, mode='r', newline=''):
        return open(self.filepath, mode=mode, newline=newline)

    def get_column_names(self):
        """
        Extracts the first row of the CSV as column names.
        Note: Since the UML doesn't specify delimiters here, 
        we assume a standard comma or handle it via the caller's logic.
        However, to be functional, we'll try to detect or use a default.
        """
        with self.open_csv(mode='r', newline='') as f:
            # We use a Sniffer to try and detect the delimiter if not specified,
            # but for strict adherence to the requirement of 'extracting',
            # we'll implement a basic reader.
            reader = csv.reader(f, delimiter=self.delimiter)
            try:
                return next(reader)
            except StopIteration:
                return []

    def get_data_rows(self):
        """
        Extracts all rows except the header.
        """
        with self.open_csv(mode='r', newline='') as f:
            reader = csv.reader(f, delimiter=self.delimiter)
            try:
                next(reader)  # Skip header
            except StopIteration:
                return []
            return [row for row in reader]
