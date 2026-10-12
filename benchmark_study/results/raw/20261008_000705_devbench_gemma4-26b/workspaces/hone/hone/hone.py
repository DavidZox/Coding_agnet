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
        # Based on the requirement to infer structure, we look for common delimiters in names
        # like ' ', '(', ')', '_', etc. However, the UML suggests a more specific logic.
        # We will implement a logic that identifies potential hierarchical separators.
        splits = []
        # Common separators used in column names to imply nesting
        separators = [' ', '(', ')', '_', '/', '-']
        for sep in separators:
            if sep in column_name:
                splits.append(sep)
        return list(set(splits))

    def get_split_suffix(self, split, column_name):
        if split in column_name:
            parts = column_name.split(split)
            if len(parts) > 1:
                return parts[-1].strip()
        return None

    def clean_split(self, split):
        return split.strip()

    def is_valid_prefix(self, prefix, base):
        return base.startswith(prefix)

    def get_nested_structure(self, parent_structure):
        # This is a placeholder for logic that might be used to traverse or build
        return parent_structure

    def get_leaves(self, structure, path, result):
        if isinstance(structure, dict):
            for key, value in structure.items():
                self.get_leaves(value, path + [key], result)
        else:
            result.append((path, structure))

    def generate_full_structure(self, column_names):
        # Generates a nested dictionary structure based on column names
        # This is a simplified version of the logic implied by the PRD/UML
        # In a real scenario, this would parse the column names to find hierarchy
        structure = {}
        for col in column_names:
            # For the purpose of this implementation, we assume a simple 
            # structure unless the schema is provided. 
            # If the column name contains a space or parenthesis, we treat it as a potential nest.
            # But the PRD says 'get_schema' generates it.
            # Let's implement a basic one-level nesting if a separator is found.
            parts = []
            # Try to split by common hierarchical indicators
            if ' ' in col:
                parts = col.split(' ', 1)
            elif '(' in col and ')' in col:
                # e.g., "age (years)" -> "age": {"years": ...}
                base = col.split('(')[0].strip()
                suffix = col.split('(')[1].split(')')[0].strip()
                parts = [base, suffix]
            else:
                parts = [col]
            
            curr = structure
            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    curr[part] = None # Leaf placeholder
                else:
                    if part not in curr:
                        curr[part] = {}
                    curr = curr[part]
        return structure

    def populate_structure_with_data(self, structure, column_names, data_rows):
        results = []
        for row in data_rows:
            # Create a flat mapping of column -> value
            row_map = dict(zip(column_names, row))
            
            # We need to build the nested object based on the 'structure' template
            # But the structure template is just keys. We need to map the actual data.
            # A better way is to use the schema or the column names directly.
            
            # Let's use a recursive approach to build the object for this row
            def build_nested(current_struct, current_row_map):
                obj = {}
                # This is tricky because 'structure' is a template.
                # We'll use the column names to find which data goes where.
                # For this implementation, we'll assume the structure keys 
                # correspond to the hierarchy of the column names.
                return obj

            # Re-implementing logic: The structure is a template of keys.
            # We will use the column names to populate the nested dict.
            nested_row = {}
            
            # Helper to insert value into nested dict based on a path
            def insert_path(target_dict, path, value):
                for part in path[:-1]:
                    if part not in target_dict:
                        target_dict[part] = {}
                    target_dict = target_dict[part]
                target_dict[path[-1]] = value

            # We need to determine the path for each column name
            for col in column_names:
                val = row_map[col]
                # Determine path for this column
                path = []
                if ' ' in col:
                    parts = col.split(' ', 1)
                    path = [parts[0].strip(), parts[1].strip()]
                elif '(' in col and ')' in col:
                    base = col.split('(')[0].strip()
                    suffix = col.split('(')[1].split(')')[0].strip()
                    path = [base, suffix]
                else:
                    path = [col]
                
                insert_path(nested_row, path, val)
            
            results.append(nested_row)
        return results

    def get_schema(self, csv_filepath):
        # In a real implementation, this would analyze the CSV to create a schema.
        # For now, it returns a basic structure.
        csv_utils = CSVUtils(csv_filepath)
        cols = csv_utils.get_column_names()
        return self.generate_full_structure(cols)

    def convert(self, csv_filepath, schema=None):
        self.set_csv_filepath(csv_filepath)
        csv_utils = CSVUtils(self.csv_filepath)
        column_names = csv_utils.get_column_names()
        data_rows = csv_utils.get_data_rows()

        if schema is None:
            # If no schema, we infer it from column names
            # The UML suggests generate_full_structure is used.
            structure = self.generate_full_structure(column_names)
        else:
            structure = schema

        # If schema is provided, we use it to guide the population.
        # The populate_structure_with_data should handle the mapping.
        
        # If schema is a dict, we use it to map CSV columns to JSON paths.
        # Let's refine populate_structure_with_data to use the schema if provided.
        
        if schema:
            # If schema is provided, it's a mapping: JSON_PATH -> CSV_COLUMN
            # e.g., {"birth": {"year": "birth year"}}
            json_struct = []
            for row in data_rows:
                row_map = dict(zip(column_names, row))
                nested_row = {}

                def fill_from_schema(schema_part, target_part, row_map):
                    if isinstance(schema_part, dict):
                        for k, v in schema_part.items():
                            if k not in target_part:
                                target_part[k] = {}
                            fill_from_schema(v, target_part[k], row_map)
                    else:
                        # schema_part is the CSV column name
                        target_part[None] = row_map.get(schema_part) # This is a bit messy

                # Correct approach for schema:
                # schema is: {"birth": {"year": "birth year"}}
                # We iterate through the schema to build the object.
                def build_with_schema(s, target):
                    for key, value in s.items():
                        if isinstance(value, dict):
                            if key not in target:
                                target[key] = {}
                            build_with_schema(value, target[key])
                        else:
                            # value is the CSV column name
                            target[key] = row_map.get(value)

                build_with_schema(schema, nested_row)
                json_struct.append(nested_row)
            return json_struct
        else:
            # Use the inferred structure logic
            return self.populate_structure_with_data(structure, column_names, data_rows)
