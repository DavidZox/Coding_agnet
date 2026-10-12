import csv
import json
import argparse
from contextlib import contextmanager
from hone.utils.csv_utils import CSVUtils
from hone.utils.json_utils import JSONUtils

class Hone:
    DEFAULT_DELIMITERS = [',', '\t', ';', '|']

    def __init__(self, delimiters=None):
        self.delimiters = delimiters if delimiters else self.DEFAULT_DELIMITERS
        self.csv_filepath = None
        self.csv = None
        self.json_utils = JSONUtils()

    def convert(self, csv_filepath, schema=None):
        self.set_csv_filepath(csv_filepath)
        csv_utils = CSVUtils(csv_filepath)
        column_names = csv_utils.get_column_names()
        data_rows = csv_utils.get_data_rows()
        if not schema:
            schema = self.get_schema(csv_filepath)
        structure = self.generate_full_structure(column_names)
        self.populate_structure_with_data(structure, column_names, data_rows)
        json_filepath = csv_filepath.replace('.csv', '.json')
        self.json_utils.output_json(structure, json_filepath)
        return structure

    def populate_structure_with_data(self, structure, column_names, data_rows):
        for row in data_rows:
            current_level = structure
            for i, value in enumerate(row):
                column_name = column_names[i]
                splits = self.get_valid_splits(column_name)
                for j, split in enumerate(splits):
                    if j < len(splits) - 1:
                        if split not in current_level:
                            current_level[split] = {}
                        current_level = current_level[split]
                    else:
                        if split in current_level:
                            if not isinstance(current_level[split], list):
                                current_level[split] = [current_level[split]]
                            current_level[split].append(value)
                        else:
                            current_level[split] = value

    def get_schema(self, csv_filepath):
        csv_utils = CSVUtils(csv_filepath)
        column_names = csv_utils.get_column_names()
        schema = {}
        for column_name in column_names:
            splits = self.get_valid_splits(column_name)
            current_level = schema
            for split in splits:
                if split not in current_level:
                    current_level[split] = {}
                current_level = current_level[split]
        return schema

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
                nested_structure[key] = value
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
                result.append((path + [key], value))
        return result

    def get_valid_splits(self, column_name):
        splits = []
        for delimiter in self.delimiters:
            if delimiter in column_name:
                splits.extend(column_name.split(delimiter))
        if not splits:
            splits = [column_name]
        return [self.clean_split(split) for split in splits]

    def get_split_suffix(self, split, column_name):
        for delimiter in self.delimiters:
            if delimiter in column_name:
                parts = column_name.split(delimiter)
                if split in parts:
                    index = parts.index(split)
                    return delimiter.join(parts[index+1:])
        return ''

    def clean_split(self, split):
        return split.strip().strip('"').strip("'")

    def is_valid_prefix(self, prefix, base):
        return base.startswith(prefix)

    def set_csv_filepath(self, csv_filepath):
        self.csv_filepath = csv_filepath

    def escape_quotes(self, string):
        return string.replace('"', '\\"').replace("'", "\\'")
