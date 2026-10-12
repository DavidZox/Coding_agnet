import json
import sys

class JSONUtils:
    @staticmethod
    def output_json(json_struct, json_filepath):
        if json_filepath:
            with open(json_filepath, 'w') as json_file:
                json.dump(json_struct, json_file, indent=4, sort_keys=True)
        else:
            json.dump(json_struct, sys.stdout, indent=4, sort_keys=True)
