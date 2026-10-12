import json
import csv

def parse_json_file(json_filepath):
    """
    Parses a JSON file and returns its content.
    """
    try:
        with open(json_filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error parsing JSON file {json_filepath}: {e}")
        return None

def parse_csv_file(csv_filepath, delimiter=','):
    """
    Parses a CSV file and returns its content as a list of dictionaries.
    """
    try:
        with open(csv_filepath, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            return list(reader)
    except IOError as e:
        print(f"Error reading CSV file {csv_filepath}: {e}")
        return None
