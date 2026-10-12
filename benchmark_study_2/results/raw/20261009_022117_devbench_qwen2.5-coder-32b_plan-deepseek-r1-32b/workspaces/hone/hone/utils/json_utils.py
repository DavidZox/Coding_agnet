import json
from contextlib import contextmanager

class Global_functions:
    @staticmethod
    def output_json(json_struct, json_filepath):
        with open(json_filepath, 'w', encoding='utf-8') as json_file:
            json.dump(json_struct, json_file, ensure_ascii=False, indent=4, sort_keys=True)

    @staticmethod
    def parse_json_file(json_filepath):
        with open(json_filepath, 'r', encoding='utf-8') as json_file:
            return json.load(json_file)

    @staticmethod
    def parse_csv_file(csv_filepath):
        import csv
        with open(csv_filepath, 'r', newline='', encoding='utf-8') as file:
            return list(csv.reader(file))

class JSONUtils(Global_functions):
    def output_json(self, json_struct, json_filepath):
        Global_functions.output_json(json_struct, json_filepath)
