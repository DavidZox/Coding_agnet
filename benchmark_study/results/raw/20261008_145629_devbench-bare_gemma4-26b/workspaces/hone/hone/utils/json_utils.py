import json
import sys

def output_json(json_struct, json_filepath):
    """
    Writes the JSON structure to the specified file or standard output.
    If json_filepath is None or empty, it writes to stdout.
    """
    try:
        # The specification requires proper indentation and sorted keys for readability.
        json_string = json.dumps(json_struct, indent=2, sort_keys=True)
        
        if json_filepath:
            with open(json_filepath, 'w', encoding='utf-8') as f:
                f.write(json_string)
        else:
            print(json_string)
    except Exception as e:
        raise e
