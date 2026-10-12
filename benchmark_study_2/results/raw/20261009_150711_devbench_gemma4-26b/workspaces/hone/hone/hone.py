import json
from hone.utils.csv_utils import CSVUtils

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
        return string.replace('"', '""')

    def get_valid_splits(self, column_name):
        valid_splits = []
        for d in self.delimiters:
            if d in column_name:
                # Check if the delimiter is not inside quotes by a simple split logic
                # In a real CSV, the parser handles this, but here we look at the column name string itself
                parts = column_name.split(d)
                if len(parts) > 1:
                    valid_splits.append(d)
        # Return the first delimiter found that actually splits the string
        return valid_splits[0] if valid_splits else None

    def get_split_suffix(self, split, column_name):
        if not split:
            return None
        parts = column_name.split(split)
        return parts[-1].strip()

    def clean_split(self, split):
        return split.strip()

    def is_valid_prefix(self, prefix, base):
        return base.startswith(prefix)

    def get_nested_structure(self, parent_structure):
        # This is a placeholder for logic if needed, 
        # but generate_full_structure handles the recursive creation.
        return parent_structure

    def get_leaves(self, structure, path, result):
        if isinstance(structure, dict):
            for k, v in structure.items():
                self.get_leaves(v, path + [k], result)
        else:
            result.append((path, structure))

    def generate_full_structure(self, column_names):
        full_structure = {}
        for col in column_names:
            parts = []
            current_col = col
            
            # Try to decompose the column name using delimiters
            while True:
                split_char = self.get_valid_splits(current_col)
                if not split_char:
                    parts.append(self.clean_split(current_col))
                    break
                
                # We need to decide if the split is a hierarchy or just a name.
                # Based on the requirement of "nested", we assume the last part is the leaf.
                # However, the UML suggests we build the structure.
                # Let's split by the first occurrence of a delimiter to build depth.
                idx = current_col.find(split_char)
                prefix = current_col[:idx].strip()
                suffix = current_col[idx+len(split_char):].strip()
                
                if not prefix:
                    parts.append(self.clean_split(current_col))
                    break
                
                # To avoid infinite loops and handle complex names, 
                # we treat the prefix as a parent and recurse on suffix.
                # But the standard way for these tasks is: prefix is parent, suffix is child.
                # We'll use a temporary dict to build.
                
                # Let's use a different approach: build path for each column
                break # exit this loop to use the path-based approach below

            # Re-implementing logic: build path for each column
            path = []
            temp_col = col
            while True:
                split_char = self.get_valid_splits(temp_col)
                if not split_char:
                    path.append(self.clean_split(temp_col))
                    break
                
                idx = temp_col.find(split_char)
                prefix = temp_col[:idx].strip()
                suffix = temp_col[idx+len(split_char):].strip()
                
                if not prefix:
                    path.append(self.clean_split(temp_col))
                    break
                
                path.append(self.clean_split(prefix))
                temp_col = suffix
            
            # Now insert path into full_structure
            curr = full_structure
            for i, p in enumerate(path):
                if i == len(path) - 1:
                    curr[p] = None # Leaf placeholder
                else:
                    if p not in curr or not isinstance(curr[p], dict):
                        curr[p] = {}
                    curr = curr[p]
        return full_structure

    def populate_structure_with_data(self, structure, column_names, data_rows):
        # structure is the template (dict)
        # column_names are the original CSV headers
        # data_rows is a list of dicts (from CSVUtils)
        
        results = []
        for row in data_rows:
            new_obj = {}
            
            # We need to map each column in the row to the nested structure
            for col_name, value in row.items():
                # Determine the path for this column
                path = []
                temp_col = col_name
                while True:
                    split_char = self.get_valid_splits(temp_col)
                    if not split_char:
                        path.append(self.clean_split(temp_col))
                        break
                    idx = temp_col.find(split_char)
                    prefix = temp_col[:idx].strip()
                    suffix = temp_col[idx+len(split_char):].strip()
                    if not prefix:
                        path.append(self.clean_split(temp_col))
                        break
                    path.append(self.clean_split(prefix))
                    temp_col = suffix
                
                # Traverse/build the path in new_obj
                curr = new_obj
                for i, p in enumerate(path):
                    if i == len(path) - 1:
                        curr[p] = value
                    else:
                        if p not in curr:
                            curr[p] = {}
                        curr = curr[p]
            results.append(new_obj)
        return results

    def get_schema(self, csv_filepath):
        csv_utils = CSVUtils(csv_filepath)
        column_names = csv_utils.get_column_names()
        return self.generate_full_structure(column_names)

    def convert(self, csv_filepath, schema=None):
        self.set_csv_filepath(csv_filepath)
        csv_utils = CSVUtils(self.csv_filepath)
        column_names = csv_utils.get_column_names()
        data_rows = csv_utils.get_data_rows()

        if schema:
            # If schema is provided, we use it to guide the structure.
            # However, the schema provided in the prompt is a mapping: 
            # {"nested_key": "csv_column_name"}
            # We need to invert this or use it to build the object.
            
            # Let's handle the schema as a template where keys are JSON keys 
            # and values are CSV column names (or nested dicts of them).
            
            def build_from_schema(s, row_data):
                res = {}
                for k, v in s.items():
                    if isinstance(v, dict):
                        res[k] = build_from_schema(v, row_data)
                    else:
                        # v is the CSV column name
                        res[k] = row_data.get(v, "")
                return res

            json_struct = []
            for row in data_rows:
                json_struct.append(build_from_schema(schema, row))
            return json_struct
        else:
            # Auto-generate structure from column names
            structure = self.generate_full_structure(column_names)
            return self.populate_structure_with_data(structure, column_names, data_rows)
