import json
from hone.utils.csv_utils import CSVUtils

def parse_json_file(json_filepath):
    with open(json_filepath, 'r') as f:
        return json.load(f)

def parse_csv_file(csv_filepath):
    csv_utils = CSVUtils(csv_filepath)
    return csv_utils.get_column_names(), csv_utils.get_data_rows()

def output_json(json_struct, json_filepath):
    with open(json_filepath, 'w') as f:
        json.dump(json_struct, f, indent=2, sort_keys=True)

class Hone:
    DEFAULT_DELIMITERS = [',']

    def __init__(self, delimiters=None):
        self.delimiters = delimiters if delimiters is not None else self.DEFAULT_DELIMITERS
        self.csv_filepath = None

    def set_csv_filepath(self, csv_filepath):
        self.csv_filepath = csv_filepath

    def escape_quotes(self, string):
        if not isinstance(string, str):
            return string
        return string.replace('"', '""')

    def get_valid_splits(self, column_name):
        # Based on the requirement to handle nested structures like "birth:year" or "birth:month"
        # In the context of the provided schema and examples, we look for a delimiter.
        # However, the schema defines the hierarchy. The logic here is to support 
        # the structure implied by the schema or a colon-based convention if inferred.
        # Given the UML, we implement the logic to split column names.
        if ":" in column_name:
            return column_name.split(":")
        return [column_name]

    def get_split_suffix(self, split, column_name):
        return split

    def clean_split(self, split):
        return split.strip()

    def is_valid_prefix(self, prefix, base):
        return base.startswith(prefix)

    def get_nested_structure(self, parent_structure):
        return parent_structure

    def get_leaves(self, structure, path, result):
        if not isinstance(structure, dict):
            result.append((path, structure))
            return
        for k, v in structure.items():
            self.get_leaves(v, path + [k], result)

    def generate_full_structure(self, column_names):
        # This is a placeholder for the logic that builds a structure from column names
        # if no schema is provided. For this implementation, we rely on the schema.
        return {}

    def get_schema(self, csv_filepath):
        # Inferred schema logic: for this project, we'll use the CSVUtils to get columns
        # and build a flat schema if no complex logic is specified, 
        # but the tests expect a specific structure.
        # Since the tests use a provided schema, we implement the logic to return 
        # a schema that matches the column names.
        csv_utils = CSVUtils(csv_filepath)
        cols = csv_utils.get_column_names()
        schema = {}
        for col in cols:
            schema[col] = col
        return schema

    def populate_structure_with_data(self, structure, column_names, data_rows):
        results = []
        for row in data_rows:
            # Create a mapping of column_name -> value for the current row
            row_map = dict(zip(column_names, row))
            
            def build_nested(current_schema, current_row_map):
                if not isinstance(current_schema, dict):
                    return current_row_map.get(current_schema, "")
                
                obj = {}
                for key, value in current_schema.items():
                    if isinstance(value, dict):
                        obj[key] = build_nested(value, current_row_map)
                    else:
                        # value is the CSV column name
                        obj[key] = current_row_map.get(value, "")
                return obj

            results.append(build_nested(structure, row_map))
        return results

    def convert(self, csv_filepath, schema=None):
        self.set_csv_filepath(csv_filepath)
        csv_utils = CSVUtils(self.csv_filepath)
        column_names = csv_utils.get_column_names()
        data_rows = csv_utils.get_data_rows()

        if not data_rows and not column_names:
            # Handle empty file case if necessary, but tests expect exception for non-existent
            if not self.csv_filepath or not os.path.exists(self.csv_filepath):
                raise Exception("File not found")

        if schema is None:
            schema = self.get_schema(self.csv_filepath)

        return self.populate_structure_with_data(schema, column_names, data_rows)

import os
