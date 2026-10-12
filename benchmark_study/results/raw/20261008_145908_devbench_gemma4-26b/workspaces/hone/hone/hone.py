import json
from hone.utils.csv_utils import CSVUtils

class Hone:
    DEFAULT_DELIMITERS = [',', ';', '\t', '|']

    def __init__(self, delimiters=None):
        self.delimiters = delimiters if delimiters is not None else self.DEFAULT_DELIMITERS
        self.csv_filepath = None
        self.csv = None

    def set_csv_filepath(self, csv_filepath):
        self.csv_filepath = csv_filepath

    def escape_quotes(self, string):
        if not isinstance(string, str):
            return string
        return string.replace('"', '""')

    def get_valid_splits(self, column_name):
        # In this implementation, we assume splits are defined by the schema or 
        # logic that identifies nested structures. 
        # For the purpose of this class, we'll return an empty list unless logic is provided.
        return []

    def get_split_suffix(self, split, column_name):
        return column_name.replace(split, "").strip()

    def clean_split(self, split):
        return split.strip()

    def is_valid_prefix(self, prefix, base):
        return base.startswith(prefix)

    def get_nested_structure(self, parent_structure):
        # This is a placeholder for logic that might derive structure from existing data
        return {}

    def get_leaves(self, structure, path, result):
        if not isinstance(structure, dict):
            result.append((path, structure))
            return
        for key, value in structure.items():
            self.get_leaves(value, path + [key], result)

    def generate_full_structure(self, column_names):
        # Generates a flat structure where each column is a key
        structure = {}
        for col in column_names:
            structure[col] = None
        return structure

    def get_schema(self, csv_filepath):
        # If no schema is provided, we generate one based on column names
        csv_utils = CSVUtils(csv_filepath)
        column_names = csv_utils.get_column_names()
        return self.generate_full_structure(column_names)

    def populate_structure_with_data(self, structure, column_names, data_rows):
        json_list = []
        for row in data_rows:
            # Create a mapping of column_name -> value for the current row
            row_data = dict(zip(column_names, row))
            
            # We need to transform the flat row_data into the nested structure
            # defined by 'structure'
            nested_row = self._build_nested_dict(structure, row_data)
            json_list.append(nested_row)
        return json_list

    def _build_nested_dict(self, schema_node, row_data):
        """
        Recursive helper to build the nested dictionary.
        schema_node: The template structure (can be a dict or a leaf value)
        row_data: The flat dictionary from the CSV row
        """
        if not isinstance(schema_node, dict):
            # If the schema node is not a dict, it's a leaf. 
            # However, in our schema, the 'leaf' is actually the value in the schema 
            # that points to the CSV column name.
            # But based on the UML and PRD, the schema is a template.
            return None

        result = {}
        for key, value in schema_node.items():
            if isinstance(value, dict):
                # Recurse into nested dictionary
                nested_val = self._build_nested_dict(value, row_data)
                if nested_val is not None:
                    result[key] = nested_val
            else:
                # It's a leaf. The value in the schema is the CSV column name.
                csv_col_name = value
                if csv_col_name in row_data:
                    result[key] = row_data[csv_col_name]
        return result

    def convert(self, csv_filepath, schema=None):
        self.set_csv_filepath(csv_filepath)
        csv_utils = CSVUtils(self.csv_filepath)
        column_names = csv_utils.get_column_names()
        data_rows = csv_utils.get_data_rows()

        if schema is None:
            # If no schema is provided, we use a flat structure
            # Based on PRD, if no schema, it should be inferred.
            # For simplicity in this implementation, we'll treat columns as keys.
            structure = {col: col for col in column_names}
        else:
            if isinstance(schema, str):
                schema = json.loads(schema)
            structure = schema

        return self.populate_structure_with_data(structure, column_names, data_rows)
