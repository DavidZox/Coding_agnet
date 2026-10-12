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
        if schema:
            structure = schema
        else:
            structure = self.generate_full_structure(column_names)
        json_struct = self.populate_structure_with_data(structure, column_names, data_rows)
        return json_struct

    def populate_structure_with_data(self, structure, column_names, data_rows):
        json_data = []
        for row in data_rows:
            data_dict = {}
            for col_name, value in zip(column_names, row):
                self._set_nested_value(data_dict, col_name, value, structure)
            json_data.append(data_dict)
        return json_data

    def _set_nested_value(self, data_dict, col_name, value, structure):
        if col_name in structure:
            if isinstance(structure[col_name], dict):
                nested_key = list(structure[col_name].keys())[0]
                if nested_key not in data_dict:
                    data_dict[nested_key] = {}
                self._set_nested_value(data_dict[nested_key], col_name, value, structure[col_name])
            else:
                data_dict[structure[col_name]] = value

    def get_schema(self, csv_filepath):
        self.set_csv_filepath(csv_filepath)
        csv_utils = CSVUtils(self.csv_filepath)
        column_names = csv_utils.get_column_names()
        return self.generate_full_structure(column_names)

    def generate_full_structure(self, column_names):
        structure = {}
        for col_name in column_names:
            splits = self.get_valid_splits(col_name)
            if len(splits) > 1:
                current_level = structure
                for split in splits[:-1]:
                    clean_split = self.clean_split(split)
                    if clean_split not in current_level:
                        current_level[clean_split] = {}
                    current_level = current_level[clean_split]
                current_level[self.clean_split(splits[-1])] = col_name
            else:
                structure[col_name] = col_name
        return structure

    def get_valid_splits(self, column_name):
        splits = []
        for delimiter in self.delimiters:
            if delimiter in column_name:
                splits = column_name.split(delimiter)
                break
        if not splits:
            splits = [column_name]
        return splits

    def clean_split(self, split):
        return self.escape_quotes(split.strip())

    def escape_quotes(self, string):
        return string.replace('""', '"').strip('"')

    def set_csv_filepath(self, csv_filepath):
        self.csv_filepath = csv_filepath
