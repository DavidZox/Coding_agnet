import csv

class CSVUtils:
    def __init__(self, csv_filepath, delimiters=None):
        """
        Initializes the CSVUtils with the given filepath.
        
        :param csv_filepath: Path to the CSV file.
        :param delimiters: List of string delimiters for parsing CSV files.
        """
        self.filepath = csv_filepath
        self.delimiters = delimiters

    def open_csv(self, mode='r', newline=''):
        """
        Opens the CSV file.
        
        :param mode: Mode in which the file is opened.
        :param newline: Newline characters to use.
        :return: A file object.
        """
        return open(self.filepath, mode=mode, newline=newline)

    def get_column_names(self, delimiter=','):
        """
        Extracts the column names from the CSV file.
        
        :param delimiter: The delimiter used in the CSV file.
        :return: A list of column names.
        """
        # If no specific delimiter is provided, try the ones from self.delimiters
        # However, the method signature expects a single delimiter.
        # We will use the provided delimiter or default to ','
        with self.open_csv(mode='r', newline='') as f:
            reader = csv.reader(f, delimiter=delimiter)
            try:
                column_names = next(reader)
                return column_names
            except StopIteration:
                return []

    def get_data_rows(self, delimiter=','):
        """
        Extracts the data rows from the CSV file.
        
        :param delimiter: The delimiter used in the CSV file.
        :return: A list of lists containing the data rows.
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
