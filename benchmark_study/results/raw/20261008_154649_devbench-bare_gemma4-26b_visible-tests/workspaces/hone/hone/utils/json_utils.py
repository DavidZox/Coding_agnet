import json

def output_json(json_struct, json_filepath):
    """
    Writes a JSON structure to a specified file with proper indentation and sorted keys.

    Args:
        json_struct (dict or list): The JSON-compatible data structure to write.
        json_filepath (str): The path to the output JSON file.
    """
    with open(json_filepath, 'w', encoding='utf-8') as f:
        json.dump(json_struct, f, indent=2, sort_keys=True)

def parse_json_file(json_filepath):
    """
    Parses a JSON file and returns its content.

    Args:
        json_filepath (str): The path to the JSON file.

    Returns:
        dict or list: The parsed JSON content.
    """
    with open(json_filepath, 'r', encoding='utf-8') as f:
        return json.load(f)
