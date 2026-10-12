class Hone:
    DEFAULT_DELIMITERS = [',']
    
    def __init__(self, delimiters=None):
        self.delimiters = delimiters if delimiters else self.DEFAULT_DELIMITERS
        self.csv_filepath = None
        self.csv = None

    def convert(self, csv_filepath, schema=None):
        self.set_csv_filepath(csv_filepath)
        column_names = self.get_column_names()
        data_rows = self.get_data_rows()
        if not schema:
            schema = self.get_schema(csv_filepath)
        structure = self.generate_full_structure(column_names)
        self.populate_structure_with_data(structure, column_names, data_rows)
        return structure

    def populate_structure_with_data(self, structure, column_names, data_rows):
        pass

    def get_schema(self, csv_filepath):
        pass

    def generate_full_structure(self, column_names):
        pass

    def get_nested_structure(self, parent_structure):
        pass

    def get_leaves(self, structure, path, result):
        pass

    def get_valid_splits(self, column_name):
        pass

    def get_split_suffix(self, split, column_name):
        pass

    def clean_split(self, split):
        pass

    def is_valid_prefix(self, prefix, base):
        pass

    def set_csv_filepath(self, csv_filepath):
        self.csv_filepath = csv_filepath

    def escape_quotes(self, string):
        pass
