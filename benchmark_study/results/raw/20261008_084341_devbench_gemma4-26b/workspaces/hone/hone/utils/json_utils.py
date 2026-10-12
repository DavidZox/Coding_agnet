import json
import sys
from hone.utils.csv_utils import CSVUtils

def output_json(json_struct, json_filepath):
    """
    Outputs the JSON structure to a file or to stdout.
    The output is indented and keys are sorted.
    """
    json_string = json.dumps(json_struct, indent=4, sort_keys=True)
    if not json_filepath:
        print(json_string)
    else:
        with open(json_filepath, 'w', encoding='utf-8') as f:
            f.write(json_string)

def parse_json_file(json_filepath):
    """
    Parses a JSON file and returns its content.
    """
    with open(json_filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def parse_csv_file(csv_filepath):
    """
    Parses a CSV file using CSVUtils and returns column names and data rows.
    """
    csv_utils = CSVUtils(csv_filepath)
    column_names = csv_utils.get_column_names()
    data_rows = csv_utils.get_data_rows()
    return column_names, data_rows
