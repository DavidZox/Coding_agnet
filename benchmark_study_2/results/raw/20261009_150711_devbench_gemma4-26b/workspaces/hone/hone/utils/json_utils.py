import json
import sys

def output_json(json_struct, json_filepath=None):
    """
    Writes the JSON structure to a file or standard output.
    The output is indented and keys are sorted for readability.
    """
    json_string = json.dumps(json_struct, indent=2, sort_keys=True)
    
    if json_filepath:
        with open(json_filepath, 'w', encoding='utf-8') as f:
            f.write(json_string)
    else:
        print(json_string)
