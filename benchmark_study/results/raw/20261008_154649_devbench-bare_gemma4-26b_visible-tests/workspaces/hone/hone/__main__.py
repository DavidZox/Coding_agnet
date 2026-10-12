import argparse
import json
import sys
from hone import Hone, output_json

def main():
    parser = argparse.ArgumentParser(description="Convert CSV files to nested JSON formats.")
    parser.add_argument('--delimiters', nargs='+', type=str, help='List of string delimiters for parsing CSV files.')
    parser.add_argument('--schema', type=str, help='JSON schema structure for the output JSON.')
    parser.add_argument('csv_filepath', type=str, help='Path to the input CSV file.')
    parser.add_argument('json_filepath', type=str, help='Path to the output JSON file.')

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
    # Note: The UML/PRD implies delimiters are used for parsing. 
    # Since CSVUtils doesn't take delimiters in __init__ per UML, 
    # we pass them to Hone which will use them.
    hone_instance = Hone(delimiters=args.delimiters)

    try:
        # Perform conversion
        json_struct = hone_instance.convert(args.csv_filepath, schema=schema)
        
        # Output result
        output_json(json_struct, args.json_filepath)
        
    except Exception as e:
        print(f"An error occurred during conversion: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
