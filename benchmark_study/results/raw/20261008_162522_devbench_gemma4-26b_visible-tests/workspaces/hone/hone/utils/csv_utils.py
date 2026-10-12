import csv

class CSVUtils:
    def __init__(self, csv_filepath, delimiters=None):
        self.filepath = csv_filepath
        self.delimiters = delimiters if delimiters is not None else [',']

    def open_csv(self, mode='r', newline='', delimiter=','):
        """Opens a CSV file with the specified mode and newline character."""
        return open(self.filepath, mode=mode, newline=newline)

    def get_column_names(self):
        """Extracts the column names from the first row of the CSV file."""
        for delimiter in self.delimiters:
            try:
                with self.open_csv(mode='r', newline='', delimiter=delimiter) as f:
                    reader = csv.reader(f, delimiter=delimiter)
                    try:
                        column_names = next(reader)
                        # If the delimiter is wrong, we might get a single long string.
                        # We check if the delimiter is actually present in the first field 
                        # (excluding cases where the delimiter is part of a quoted string, 
                        # but csv.reader handles that). A better heuristic: if we have 
                        # only one column and it contains other delimiters, it's likely wrong.
                        if len(column_names) == 1:
                            is_likely_wrong = False
                            for other_delim in self.delimiters:
                                if other_delim != delimiter and other_delim in column_names[0]:
                                    is_likely_wrong = True
                                    break
                            if is_likely_wrong:
                                continue
                        return column_names, delimiter
                    except StopIteration:
                        continue
            except Exception:
                continue
        return [], None

    def get_data_rows(self, delimiter=None):
        """Extracts all data rows from the CSV file, excluding the header."""
        # If delimiter is provided, use it directly. Otherwise, try to find it.
        if delimiter is None:
            # This part is a fallback, but the design suggests passing the delimiter from get_column_names
            column_names_res = self.get_column_names()
            if not column_names_res or column_names_res[0] == []:
                return []
            column_names, delimiter = column_names_res

        try:
            with self.open_csv(mode='r', newline='', delimiter=delimiter) as f:
                reader = csv.reader(f, delimiter=delimiter)
                try:
                    next(reader)  # Skip header
                    rows = [row for row in reader]
                    return rows
                except StopIteration:
                    return []
        except Exception:
            return []
