import csv
import json
from hone.utils.csv_utils import CSVUtils

class Hone:
    DEFAULT_DELIMITERS = [',', '\t', ';', '|']

    def __init__(self, delimiters=None):
        self.delimiters = delimiters if delimiters else self.DEFAULT_DELIMITERS
        self.csv_filepath = None
        self.csv = None

    def convert(self, csv_filepath, schema=None):
        self.set_csv_filepath(csv_filepath)
        csv_utils = CSVUtils(self.csv_filepath)
        column_names = csv_utils.get_column_names()
        data_rows = csv_utils.get_data_rows()
        if not schema:
            schema = self.get_schema(csv_filepath)
        structure = self.generate_full_structure(column_names)
        self.populate_structure_with_data(structure, column_names, data_rows)
        return structure

    def populate_structure_with_data(self, structure, column_names, data_rows):
        for row in data_rows:
            current_level = structure
            for i, value in enumerate(row):
                column_name = column_names[i]
                if column_name in current_level:
                    current_level = current_level[column_name]
                    if isinstance(current_level, list):
                        current_level[-1][column_name] = value
                    else:
                        current_level[column_name] = value
                else:
                    current_level[column_name] = value

    def get_schema(self, csv_filepath):
        csv_utils = CSVUtils(csv_filepath)
        column_names = csv_utils.get_column_names()
        return self.generate_full_structure(column_names)

    def generate_full_structure(self, column_names):
        structure = {}
        for column_name in column_names:
            splits = self.get_valid_splits(column_name)
            current_level = structure
            for split in splits:
                if split not in current_level:
                    current_level[split] = {}
                current_level = current_level[split]
        return structure

    def get_nested_structure(self, parent_structure):
        nested_structure = {}
        for key, value in parent_structure.items():
            if isinstance(value, dict):
                nested_structure[key] = self.get_nested_structure(value)
            else:
                nested_structure[key] = []
        return nested_structure

    def get_leaves(self, structure, path=None, result=None):
        if path is None:
            path = []
        if result is None:
            result = []
        for key, value in structure.items():
            if isinstance(value, dict):
                self.get_leaves(value, path + [key], result)
            else:
                result.append('.'.join(path + [key]))
        return result

    def get_valid_splits(self, column_name):
        splits = []
        for delimiter in self.delimiters:
            if delimiter in column_name:
                splits.extend(self.get_split_suffix(delimiter, column_name))
        if not splits:
            splits.append(column_name)
        return splits

    def get_split_suffix(self, split, column_name):
        suffixes = []
        parts = column_name.split(split)
        for i, part in enumerate(parts):
            cleaned_part = self.clean_split(part)
            if cleaned_part:
                suffixes.append(cleaned_part)
        return suffixes

    def clean_split(self, split):
        cleaned = split.strip()
        if cleaned:
            return self.escape_quotes(cleaned)
        return None

    def is_valid_prefix(self, prefix, base):
        return base.startswith(prefix)

    def set_csv_filepath(self, csv_filepath):
        self.csv_filepath = csv_filepath

    def escape_quotes(self, string):
        return string.replace('"', '\\"')
