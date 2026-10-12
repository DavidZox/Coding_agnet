import json
from hone.utils.csv_utils import CSVUtils

class Hone:
    DEFAULT_DELIMITERS = [',', ';', '\t', '|']

    def __init__(self, delimiters=None):
        self.delimiters = delimiters if delimiters is not None else self.DEFAULT_DELIMITERS
        self.csv_filepath = None
        self.csv = None

    def set_csv_filepath(self, csv_filepath):
        self.csv_filepath = csv_filepath

    def escape_quotes(self, string):
        if not isinstance(string, str):
            return string
        return string.replace('"', '""')

    def get_valid_splits(self, column_name):
        # Logic to determine if a column name represents a nested structure
        # Based on the requirement to support schema or inferred structure
        # For this implementation, we assume a split is valid if it contains a separator
        # that matches the schema's nesting logic (e.g., 'birth year' -> 'birth': {'year': ...})
        # However, the UML suggests specific methods for splitting.
        # We will implement a basic version that looks for spaces or common delimiters.
        return [column_name]

    def get_split_suffix(self, split, column_name):
        # Returns the part of the column name after the split
        if split in column_name:
            return column_name.split(split, 1)[1].strip()
        return column_name

    def clean_split(self, split):
        return split.strip().strip('"').strip("'")

    def is_valid_prefix(self, prefix, base):
        return base.startswith(prefix)

    def get_nested_structure(self, parent_structure):
        # This is a placeholder for logic that might transform a flat structure to nested
        return parent_structure

    def get_leaves(self, structure, path, result):
        if isinstance(structure, dict):
            for key, value in structure.items():
                new_path = path + [key]
                self.get_leaves(value, new_path, result)
        else:
            result.append((path, structure))

    def generate_full_structure(self, column_names):
        # Generates a flat dictionary mapping column names to themselves
        return {name: name for name in column_names}

    def get_schema(self, csv_filepath):
        # In a real scenario, this might infer schema. 
        # For now, it returns None to trigger automatic generation in convert()
        return None

    def populate_structure_with_data(self, structure, column_names, data_rows):
        json_list = []
        for row in data_rows:
            # Create a mapping of column_name -> value for this row
            row_data = dict(zip(column_names, row))
            
            # The structure can be a schema (dict) or a flat mapping
            # If structure is a schema, we follow its hierarchy
            current_row_json = {}
            
            if isinstance(structure, dict):
                # If structure is a schema, we need to traverse it
                def build_nested(schema_part, data_map, target_dict):
                    for key, value in schema_part.items():
                        if isinstance(value, dict):
                            # Nested level
                            target_dict[key] = {}
                            build_nested(value, data_map, target_dict[key])
                        else:
                            # Leaf level: value is the CSV column name
                            csv_col = value
                            if csv_col in data_map:
                                target_dict[key] = data_map[csv_col]
                
                build_nested(structure, row_data, current_row_json)
            else:
                # If structure is just a flat mapping (generated)
                for col_name, target_key in structure.items():
                    if col_name in row_data:
                        current_row_json[target_key] = row_data[col_name]
            
            json_list.append(current_row_json)
        return json_list

    def convert(self, csv_filepath, schema=None):
        self.set_csv_filepath(csv_filepath)
        csv_utils = CSVUtils(csv_filepath)
        
        # Try to find the correct delimiter from the allowed list
        column_names = []
        data_rows = []
        
        # We attempt to read the file with each delimiter until successful
        # In a real implementation, CSVUtils would handle this or we'd check the file
        # For this task, we assume CSVUtils.get_column_names/get_data_rows uses the first valid delimiter
        # or we pass the delimiter if CSVUtils supported it. 
        # Since UML shows CSVUtils(csv_filepath), we assume it handles it internally.
        
        column_names = csv_utils.get_column_names()
        data_rows = csv_utils.get_data_rows()

        if schema is None:
            # Generate a flat structure if no schema is provided
            structure = self.generate_full_structure(column_names)
        else:
            structure = schema

        json_struct = self.populate_structure_with_data(structure, column_names, data_rows)
        return json_struct
