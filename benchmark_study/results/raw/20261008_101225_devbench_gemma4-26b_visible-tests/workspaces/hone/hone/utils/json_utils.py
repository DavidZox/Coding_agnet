import json
import sys

def output_json(json_struct, json_filepath):
    """
    Outputs the JSON structure to a file or to standard output.
    
    Args:
        json_struct (dict or list): The JSON-serializable structure to output.
        json_filepath (str): The path to the output file. If None or empty, outputs to stdout.
    """
    json_string = json.dumps(json_struct, indent=2, sort_keys=True)
    
    if json_filepath:
        with open(json_filepath, 'w', encoding='utf-8') as f:
            f.write(json_string)
    else:
        print(json_string)
