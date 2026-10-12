import json
import sys

def output_json(json_struct, json_filepath):
    """
    Outputs the JSON structure to a file or to standard output.
    Ensures proper indentation and sorted keys for readability.
    """
    json_string = json.dumps(json_struct, indent=2, sort_keys=True)
    
    if json_filepath:
        with open(json_filepath, 'w', encoding='utf-8') as f:
            f.write(json_string)
    else:
        sys.stdout.write(json_string + '\n')

def parse_json_file(json_filepath):
    """
    Parses a JSON file and returns its content.
    """
    with open(json_filepath, 'r', encoding='utf-8') as f:
        return json.load(f)
