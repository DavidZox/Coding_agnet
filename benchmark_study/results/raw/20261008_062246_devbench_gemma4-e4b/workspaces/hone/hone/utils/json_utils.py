import json
from typing import Any, Dict, List

class JSONUtils:
    """
    Utility class for handling JSON file operations.
    """
    def __init__(self, delimiters: List[str] = None):
        """
        Initializes JSONUtils.

        Args:
            delimiters: List of string delimiters for CSV parsing (as per UML spec).
        """
        self.delimiters = delimiters if delimiters is not None else []

    def output_json(self, json_struct: Any, json_filepath: str) -> None:
        """
        Writes a JSON structure to a specified file path.

        Args:
            json_struct: The data structure (dict or list) to write as JSON.
            json_filepath: The path to the output JSON file.
        """
        with open(json_filepath, 'w', encoding='utf-8') as f:
            # Ensure indentation=2 and keys are sorted
            json.dump(json_struct, f, indent=2, sort_keys=True)

    def write_to_stdout(self, json_struct: Any) -> None:
        """
        Writes a JSON structure to standard output in a formatted manner.

        Args:
            json_struct: The data structure (dict or list) to print as JSON.
        """
        # Ensure indentation=2 and keys are sorted for stdout readability
        print(json.dumps(json_struct, indent=2, sort_keys=True))
