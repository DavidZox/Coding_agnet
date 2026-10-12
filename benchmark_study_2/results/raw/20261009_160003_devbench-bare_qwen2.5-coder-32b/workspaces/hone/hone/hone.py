import csv
import json
import os
from hone.utils.csv_utils import CSVUtils
from hone.utils.json_utils import output_json

class Hone:
    DEFAULT_DELIMITERS = [',', ';', '\t']

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
            for i, column in enumerate(column_names):
                value = self.escape_quotes(row[i])
                if column in current_level:
                    current_level = current_level[column]
                    if isinstance(current_level, list):
                        current_level[-1][column] = value
                    else:
                        current_level[column] = value
                else:
                    current_level[column] = value
                    current_level = current_level[column]

    def get_schema(self, csv_filepath):
        csv_utils = CSVUtils(csv_filepath)
        column_names = csv_utils.get_column_names()
        return self.generate_full_structure(column_names)

    def generate_full_structure(self, column_names):
        structure = {}
        for column in column_names:
            nested_structure = self.get_nested_structure(structure)
            leaves = self.get_leaves(nested_structure, [], [])
            for leaf in leaves:
                valid_splits = self.get_valid_splits(leaf)
                if valid_splits:
                    split_suffix = self.get_split_suffix(valid_splits[0], leaf)
                    clean_split = self.clean_split(split_suffix)
                    if clean_split:
                        structure = self.insert_structure(structure, leaf, clean_split)
        return structure

    def get_nested_structure(self, parent_structure):
        nested_structure = parent_structure.copy()
        for key, value in parent_structure.items():
            if isinstance(value, dict):
                nested_structure[key] = self.get_nested_structure(value)
        return nested_structure

    def get_leaves(self, structure, path, result):
        if isinstance(structure, dict):
            for key, value in structure.items():
                self.get_leaves(value, path + [key], result)
        else:
            result.append('.'.join(path))
        return result

    def get_valid_splits(self, column_name):
        valid_splits = []
        for delimiter in self.delimiters:
            if delimiter in column_name:
                valid_splits.append(delimiter)
        return valid_splits

    def get_split_suffix(self, split, column_name):
        parts = column_name.split(split)
        return parts[-1]

    def clean_split(self, split):
        return split.strip()

    def is_valid_prefix(self, prefix, base):
        return base.startswith(prefix)

    def set_csv_filepath(self, csv_filepath):
        self.csv_filepath = csv_filepath

    def escape_quotes(self, string):
        return string.replace('""', '"').strip('"')

    def insert_structure(self, structure, leaf, clean_split):
        keys = leaf.split('.')
        for key in keys[:-1]:
            if key not in structure:
                structure[key] = {}
            structure = structure[key]
        last_key = keys[-1]
        if last_key not in structure:
            structure[last_key] = {}
        structure[last_key][clean_split] = ""
        return structure
