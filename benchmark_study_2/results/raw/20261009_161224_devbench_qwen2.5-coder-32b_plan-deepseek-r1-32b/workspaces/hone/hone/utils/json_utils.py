import json
import sys

class JSONUtils:
    def __init__(self, json_filepath=None):
        self.json_filepath = json_filepath

    def output_json(self, json_struct, json_filepath=None):
        if json_filepath is None:
            json_filepath = self.json_filepath
        if json_filepath:
            with open(json_filepath, 'w') as json_file:
                json.dump(json_struct, json_file, indent=4, sort_keys=True)
        else:
            json.dump(json_struct, sys.stdout, indent=4, sort_keys=True)

    def parse_json_file(self, json_filepath):
        with open(json_filepath, 'r') as json_file:
            return json.load(json_file)
