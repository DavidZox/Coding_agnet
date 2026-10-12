import json
import sys

def output_json(json_struct, json_filepath):
    """
    Outputs the JSON structure to a file or to standard output.
    If json_filepath is None or an empty string, outputs to stdout.
    """
    json_string = json.dumps(json_struct, indent=2, sort_keys=True)
    
    if not json_filepath:
        print(json_string)
    else:
        with open(json_filepath, 'w', encoding='utf-8') as f:
            f.write(json_string)
