import json

def output_json(json_struct, json_filepath):
    with open(json_filepath, 'w', encoding='utf-8') as jsonfile:
        json.dump(json_struct, jsonfile, ensure_ascii=False, indent=4, sort_keys=True)
