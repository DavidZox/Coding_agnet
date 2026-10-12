import csv

class CSVUtils:
    def __init__(self, csv_filepath):
        self.filepath = csv_filepath
        self._delimiter = None
        self._column_names = None
        self._data_rows = None

    def open_csv(self, mode='r', newline=''):
        return open(self.filepath, mode=mode, newline=newline)

    def _detect_dialect(self):
        if self._delimiter is not None:
            return

        with self.open_csv(mode='r', newline='') as f:
            sample = f.read(8192)
            f.seek(0)
            if not sample:
                self._delimiter = ','
                return

            # Try to find the best delimiter by checking which one produces the most columns
            best_delimiter = ','
            max_cols = -1
            
            lines = sample.splitlines()
            if not lines:
                self._delimiter = ','
                return
            
            first_line = lines[0]
            
            for d in [',', ';', '\t', '|']:
                try:
                    # Use a small sample to test each delimiter
                    test_reader = csv.reader([first_line], delimiter=d)
                    cols = next(test_reader)
                    if len(cols) > max_cols:
                        max_cols = len(cols)
                        best_delimiter = d
                except Exception:
                    continue

            # If Sniffer can provide a more specific dialect, use it
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=',;\t|')
                self._delimiter = dialect.delimiter
            except Exception:
                # Fallback to the best detected delimiter
                self._delimiter = best_delimiter

    def get_column_names(self):
        # Since the UML specifies no delimiter argument, we must rely on 
        # the default behavior or a mechanism to handle delimiters.
        # However, to satisfy the requirement of being used by Hone to detect delimiters,
        # and given the UML constraint, we will use a default comma but 
        # the Hone class should ideally handle the delimiter logic.
        # To fix the error where Hone tries to pass a delimiter, 
        # we must ensure this method matches the UML signature.
        if self._column_names is not None:
            return self._column_names

        self._detect_dialect()
        
        with self.open_csv(mode='r', newline='') as f:
            reader = csv.reader(f, delimiter=self._delimiter)
            try:
                self._column_names = next(reader)
            except StopIteration:
                self._column_names = []
        
        return self._column_names

    def get_data_rows(self):
        # To ensure consistency with get_column_names, we need to find the same delimiter.
        # However, the Hone class should ideally pass the delimiter to avoid re-detection issues.
        # Since the UML doesn't allow passing it to get_data_rows, we must detect it here.
        if self._data_rows is not None:
            return self._data_rows

        # Ensure column names and delimiter are already determined
        self.get_column_names()

        with self.open_csv(mode='r', newline='') as f:
            reader = csv.reader(f, delimiter=self._delimiter)
            try:
                next(reader)  # Skip header
                self._data_rows = [row for row in reader]
            except StopIteration:
                self._data_rows = []
        
        return self._data_rows
