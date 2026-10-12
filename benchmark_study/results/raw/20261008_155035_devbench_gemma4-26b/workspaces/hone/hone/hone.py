import json
from hone.utils.csv_utils import CSVUtils
from hone.utils.json_utils import output_json

class Hone:
    DEFAULT_DELIMITERS = [',', ';', '\t']

    def __init__(self, delimiters=None):
        self.delimiters = delimiters if delimiters is not None else self.DEFAULT_DELIMITERS
        self.csv_filepath = None
        self.csv = None

    def set_csv_filepath(self, csv_filepath):
        self.csv_filepath = csv_filepath

    def escape_quotes(self, string):
        if not isinstance(string, str):
            return string
        return string.replace('"', '\"')

    def get_valid_splits(self, column_name):
        splits = []
        for d in self.delimiters:
            if d in column_name:
                parts = column_name.split(d)
                for i in range(1, len(parts)):
                    prefix = d.join(parts[:i])
                    suffix = d.join(parts[i:])
                    splits.append((prefix, suffix))
        return splits

    def get_split_suffix(self, split, column_name):
        # This is a helper to find which suffix belongs to which split
        # In this implementation, we return the suffix part of the tuple
        return split[1]

    def clean_split(self, split):
        return split.strip()

    def is_valid_prefix(self, prefix, base):
        return base.startswith(prefix)

    def get_nested_structure(self, parent_structure):
        # Returns a copy of the structure to be used as a template for nesting
        import copy
        return copy.deepcopy(parent_structure)

    def get_leaves(self, structure, path, result):
        if not isinstance(structure, dict):
            result.append((path, structure))
            return
        for key, value in structure.items():
            new_path = path + [key]
            self.get_leaves(value, new_path, result)

    def generate_full_structure(self, column_names):
        # Generates a flat structure where each column name is a key
        structure = {}
        for col in column_names:
            structure[col] = None
        return structure

    def populate_structure_with_data(self, structure, column_names, data_rows):
        json_list = []
        for row in data_rows:
            row_dict = dict(zip(column_names, row))
            nested_row = {}
            
            # We need to map the flat row_dict into the hierarchical structure
            # This is a complex task. We'll use a recursive approach based on the schema.
            
            def build_nested(current_schema, current_row_data):
                if not isinstance(current_schema, dict):
                    # If schema is not a dict, it's a leaf node (the actual CSV column name)
                    return current_row_data.get(current_schema)
                
                res = {}
                for key, val in current_schema.items():
                    if isinstance(val, dict):
                        res[key] = build_nested(val, current_row_data)
                    else:
                        # val is the CSV column name
                        res[key] = current_row_data.get(val)
                return res

            # If structure is the schema, we use it. 
            # If structure is just a placeholder, we'd need to infer.
            # Based on UML, convert() calls populate_structure_with_data.
            # We assume 'structure' passed here is the schema.
            
            # However, the UML suggests structure is the target. 
            # Let's implement the logic to fill the schema.
            
            # If structure is a schema (dict), we use it to build the object.
            # If structure is just a list of columns, we can't nest without knowing how.
            # But the PRD says we can use a provided schema.
            
            # Let's check if structure is a dict (schema)
            if isinstance(structure, dict):
                nested_row = build_nested(structure, row_dict)
            else:
                # Fallback to flat if no schema provided
                nested_row = row_dict
                
            json_list.append(nested_row)
        return json_list

    def get_schema(self, csv_filepath):
        # This method is intended to infer a schema if none is provided.
        # For this implementation, we'll return a simple flat schema if we can't infer.
        csv_utils = CSVUtils(csv_filepath, self.delimiters)
        cols = csv_utils.get_column_names()
        return {col: col for col in cols}

    def convert(self, csv_filepath, schema=None):
        self.set_csv_filepath(csv_filepath)
        csv_utils = CSVUtils(csv_filepath, self.delimiters)
        column_names = csv_utils.get_column_names()
        data_rows = csv_utils.get_data_rows()

        if schema is None:
            # If schema is a string (from CLI), parse it
            if isinstance(schema, str):
                try:
                    schema = json.loads(schema)
                except json.JSONDecodeError:
                    schema = self.get_schema(csv_filepath)
            else:
                schema = self.get_schema(csv_filepath)

        # The structure to populate is the schema
        json_struct = self.populate_structure_with_data(schema, column_names, data_rows)
        return json_struct
