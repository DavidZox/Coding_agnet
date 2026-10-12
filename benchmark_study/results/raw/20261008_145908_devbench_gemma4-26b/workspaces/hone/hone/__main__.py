import argparse
import json
import sys
from hone import Hone
from hone.utils.json_utils import output_json

def main():
    parser = argparse.ArgumentParser(description="Convert CSV files to nested JSON formats.")
    
    parser.add_argument(
        '--delimiters', 
        nargs='+', 
        type=str, 
        help='List of string delimiters for parsing CSV files.'
    )
    parser.add_argument(
        '--schema', 
        type=str, 
        help='JSON schema structure for the output JSON as a string.'
    )
    parser.add_argument(
        'csv_filepath', 
        type=str, 
        help='Path to the input CSV file.'
    )
    parser.add_argument(
        'json_filepath', 
        type=str, 
        help='Path to the output JSON file. If empty or "-", output to stdout.'
    )

    args = parser.parse_args()

    # Initialize Hone with delimiters
    # If no delimiters provided, Hone will use its internal DEFAULT_DELIMITERS
    hone_instance = Hone(delimiters=args.delimiters)

    # Parse schema if provided
    schema = None
    if args.schema:
        try:
            schema = json.loads(args.schema)
        except json.JSONDecodeError as e:
            print(f"Error parsing schema JSON: {e}", file=sys.stderr)
            sys.exit(1)

    try:
        # Perform conversion
        json_struct = hone_instance.convert(args.csv_filepath, schema)

        # Determine output destination
        # If json_filepath is empty string, None, or "-", output to stdout
        if not args.json_filepath or args.json_filepath == "-":
            output_json(json_struct, None)
        else:
            output_json(json_struct, args.json_filepath)

    except Exception as e:
        print(f"An error occurred during conversion: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
