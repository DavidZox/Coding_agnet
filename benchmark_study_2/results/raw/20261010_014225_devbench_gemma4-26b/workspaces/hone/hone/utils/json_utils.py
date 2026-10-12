import json
import sys

def output_json(json_struct, json_filepath):
    """
    Writes the JSON structure to a file or to standard output.
    The JSON is formatted with proper indentation and sorted keys.
    """
    json_string = json.dumps(json_struct, indent=2, sort_keys=True)
    
    if json_filepath is None or json_filepath == "" or json_filepath == "stdout":
        print(json_string)
    else:
        with open(json_filepath, 'w', encoding='utf-8') as f:
            f.write(json_string)
