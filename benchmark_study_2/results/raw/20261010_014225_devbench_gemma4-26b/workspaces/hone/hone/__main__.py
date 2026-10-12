import argparse
import json
import sys
from hone import Hone
from hone.utils.json_utils import output_json

def main():
    parser = argparse.ArgumentParser(description="Convert CSV files to nested JSON formats.")
    
    parser.add_argument(
        "--delimiters", 
        nargs="+", 
        help="List of string delimiters for parsing CSV files."
    )
    parser.add_argument(
        "--schema", 
        type=str, 
        help="JSON schema structure for the output JSON."
    )
    parser.add_argument(
        "csv_filepath", 
        help="Path to the input CSV file."
    )
    parser.add_argument(
        "json_filepath", 
        help="Path to the output JSON file. Use '-' to output to stdout."
    )

    args = parser.parse_args()

    # Parse schema if provided
    schema = None
    if args.schema:
        try:
            schema = json.loads(args.schema)
        except json.JSONDecodeError as e:
            print(f"Error parsing schema JSON: {e}", file=sys.stderr)
            sys.exit(1)

    # Initialize Hone
    # If delimiters are not provided, Hone will use its internal default
    hone_instance = Hone(delimiters=args.delimiters)

    try:
        # Perform conversion
        json_struct = hone_instance.convert(args.csv_filepath, schema)
        
        # Determine output destination
        # If json_filepath is '-', output to stdout via json_utils
        # Based on the requirement to use json_utils.output_json
        output_path = None if args.json_filepath == "-" else args.json_filepath
        
        output_json(json_struct, output_path)

    except Exception as e:
        print(f"An error occurred during conversion: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
