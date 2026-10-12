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
        # Logic to determine if a column name implies a nested structure
        # Based on the requirement to handle nested structures via schema or inference
        # For inference, we look for patterns like 'parent.child' or 'parent { child }'
        # However, the UML suggests specific methods for splitting.
        # We will implement a simple split by '.' as a default inference mechanism.
        if '.' in column_name:
            return column_name.split('.')
        return [column_name]

    def get_split_suffix(self, split, column_name):
        # This is a placeholder for more complex splitting logic if needed
        return split

    def clean_split(self, split):
        return split.strip()

    def is_valid_prefix(self, prefix, base):
        return base.startswith(prefix)

    def get_nested_structure(self, parent_structure):
        # Returns a copy of the structure to be used for nesting
        return parent_structure.copy()

    def get_leaves(self, structure, path, result):
        if not isinstance(structure, dict):
            result.append((path, structure))
            return
        for k, v in structure.items():
            self.get_leaves(v, path + [k], result)

    def generate_full_structure(self, column_names):
        # Generates a nested dictionary structure from column names
        # If column names are 'a.b', it creates {'a': {'b': {}}}
        root = {}
        for col in column_names:
            parts = self.get_valid_splits(col)
            current = root
            for part in parts:
                clean_part = self.clean_split(part)
                if clean_part not in current:
                    current[clean_part] = {}
                current = current[clean_part]
        return root

    def populate_structure_with_data(self, structure, column_names, data_rows):
        results = []
        for row in data_rows:
            # Create a deep copy of the structure template
            item = json.loads(json.dumps(structure))
            
            # Map row data to the structure
            # We need to find the 'leaf' nodes in the structure to place the data
            for col_idx, col_name in enumerate(column_names):
                if col_idx < len(row):
                    val = row[col_idx]
                    parts = self.get_valid_splits(col_name)
                    
                    current = item
                    for i, part in enumerate(parts):
                        clean_part = self.clean_split(part)
                        if i == len(parts) - 1:
                            # It's a leaf
                            current[clean_part] = val
                        else:
                            # It's a branch
                            if clean_part not in current or not isinstance(current[clean_part], dict):
                                current[clean_part] = {}
                            current = current[clean_part]
            results.append(item)
        return results

    def get_schema(self, csv_filepath):
        # If no schema is provided, we infer it from the CSV structure
        # For this implementation, we'll use the column names to build a schema
        csv_util = CSVUtils(csv_filepath, self.delimiters)
        column_names = csv_util.get_column_names()
        
        # A schema in this context is a mapping: JSON_PATH -> CSV_COLUMN_NAME
        # If we follow the 'small_cats_dataset' example:
        # "birth": {"year": "birth year", ...}
        # We'll implement a logic that builds this mapping.
        
        # For simplicity in this task, we'll build a schema that matches the 
        # structure inferred from column names.
        schema = {}
        for col in column_names:
            parts = self.get_valid_splits(col)
            current = schema
            for i, part in enumerate(parts):
                clean_part = self.clean_split(part)
                if i == len(parts) - 1:
                    current[clean_part] = col
                else:
                    if clean_part not in current or not isinstance(current[clean_part], dict):
                        current[clean_part] = {}
                    current = current[clean_part]
        return schema

    def convert(self, csv_filepath, schema=None):
        self.set_csv_filepath(csv_filepath)
        csv_util = CSVUtils(csv_filepath, self.delimiters)
        column_names = csv_util.get_column_names()
        data_rows = csv_util.get_data_rows()

        if schema is None:
            # If schema is a string (from CLI), parse it
            if isinstance(schema, str):
                try:
                    schema = json.loads(schema)
                except json.JSONDecodeError:
                    # If it's not valid JSON, treat it as a raw string or handle error
                    schema = {}
            
            # If schema is still empty, generate it from column names
            if not schema:
                # We use the structure-based approach
                # First, build the template structure
                structure_template = self.generate_full_structure(column_names)
                # Then populate
                return self.populate_structure_with_data(structure_template, column_names, data_rows)
        else:
            # If schema is provided, we use it to guide the construction
            # The schema defines the hierarchy.
            # Example schema: {"birth": {"year": "birth year"}}
            # We need to map CSV columns to this structure.
            
            # 1. Build the template from the schema keys
            def build_template(s):
                if not isinstance(s, dict):
                    return None
                template = {}
                for k, v in s.items():
                    if isinstance(v, dict):
                        template[k] = build_template(v)
                    else:
                        template[k] = None # Leaf placeholder
                return template

            template = build_template(schema)
            
            # 2. Populate the template using the schema mapping
            results = []
            for row in data_rows:
                # Create a deep copy of the template
                item = json.loads(json.dumps(template))
                
                # Create a mapping of CSV column name -> value for this row
                row_map = {}
                for idx, col in enumerate(column_names):
                    if idx < len(row):
                        row_map[col] = row[idx]
                
                # Recursive function to fill the item based on schema
                def fill(current_item, current_schema, mapping):
                    for key, val in current_schema.items():
                        if isinstance(val, dict):
                            fill(current_item[key], val, mapping)
                        else:
                            # val is the CSV column name
                            current_item[key] = mapping.get(val, "")
                
                fill(item, schema, row_map)
                results.append(item)
            return results

        # Fallback for the case where schema is provided but logic above is skipped
        # This part is reached if schema was provided and we didn't return in the 'else'
        return []
