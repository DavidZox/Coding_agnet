import json
from typing import Any, Dict, List, Union

class JSONUtils:
    """
    Utility class for handling JSON file operations.
    """
    
    @staticmethod
    def output_json(json_struct: Union[Dict[str, Any], List[Any]], json_filepath: str) -> None:
        """
        Writes a JSON structure to a specified file path with indentation and sorted keys.

        :param json_struct: The Python dictionary or list to write as JSON.
        :param json_filepath: The path to the output JSON file.
        :raises IOError: If there is an error writing to the file.
        """
        try:
            with open(json_filepath, 'w', encoding='utf-8') as f:
                json.dump(json_struct, f, indent=2, sort_keys=True)
        except IOError as e:
            raise IOError(f"Error writing JSON to file {json_filepath}: {e}")

    @staticmethod
    def parse_json_file(json_filepath: str) -> Union[Dict[str, Any], List[Any]]:
        """
        Reads and parses a JSON file.

        :param json_filepath: Path to the JSON file.
        :return: The parsed JSON object (dict or list).
        :raises FileNotFoundError: If the file is not found.
        :raises json.JSONDecodeError: If the file content is not valid JSON.
        """
        try:
            with open(json_filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"JSON file not found at path: {json_filepath}")
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(f"Error decoding JSON from file {json_filepath}: {e.msg}", e.doc, e.pos)

# Global functions (as per UML_class.md, though they are often better placed in hone.py or a dedicated global module)
# Since the UML suggests Global_functions hosts these, we define them here for completeness if they are to be used directly.

def output_json(json_struct: Union[Dict[str, Any], List[Any]], json_filepath: str) -> None:
    """
    Writes a JSON structure to a specified file path with indentation and sorted keys.

    :param json_struct: The Python dictionary or list to write as JSON.
    :param json_filepath: The path to the output JSON file.
    """
    JSONUtils.output_json(json_struct, json_filepath)

def parse_json_file(json_filepath: str) -> Union[Dict[str, Any], List[Any]]:
    """
    Reads and parses a JSON file.

    :param json_filepath: Path to the JSON file.
    :return: The parsed JSON object.
    """
    return JSONUtils.parse_json_file(json_filepath)
