import json
import sys

def output_json(json_struct, json_filepath):
    """
    Outputs the given JSON structure to a file or to standard output.
    
    Args:
        json_struct (dict or list): The JSON data structure to output.
        json_filepath (str): The path to the output JSON file. 
                             If None, empty string, or 'stdout', outputs to stdout.
    """
    # Format the JSON with indentation and sorted keys for readability
    json_string = json.dumps(json_struct, indent=2, sort_keys=True)
    
    if not json_filepath or json_filepath.lower() == 'stdout':
        print(json_string)
    else:
        try:
            with open(json_filepath, 'w', encoding='utf-8') as f:
                f.write(json_string)
        except IOError as e:
            print(f"Error writing to file {json_filepath}: {e}", file=sys.stderr)
            sys.exit(1)
