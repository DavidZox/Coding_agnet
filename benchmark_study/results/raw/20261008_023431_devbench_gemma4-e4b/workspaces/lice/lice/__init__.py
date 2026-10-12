__version__ = "0.1.0"

import argparse
import sys
# Import core logic without immediate execution dependency in __init__.py
# We will call core.main() only when the script is run directly via __main__
from .core import main as core_main

def main(args: argparse.Namespace):
    """
    Main entry point for the lice CLI.
    Parses command-line arguments and delegates to core.main.
    """
    # When called from tests, args are pre-parsed. 
    # When called from CLI, args will be None/uninitialized if we rely solely on this signature.
    # We must handle the CLI execution path separately or ensure the test runner provides the correct context.
    
    if args is None:
        # Fallback for direct CLI execution
        parser = argparse.ArgumentParser(
            description="Lice License Generator: Automates the creation of open-source license files."
        )

        # Positional argument: license type
        parser.add_argument(
            "license",
            type=str,
            nargs='?',  # Makes it optional if we only want to run --vars or similar
            help="The type of license to generate (e.g., mit, gpl3, bsd3)."
        )

        # Optional arguments
        parser.add_argument(
            "-o", "--org",
            type=str,
            default=None,
            help="The organization under which the license is registered."
        )
        parser.add_argument(
            "-p", "--proj",
            type=str,
            default=None,
            help="The project name for which the license is generated."
        )
        parser.add_argument(
            "-t", "--template",
            type=str,
            default=None,
            help="The path to a custom license template file."
        )
        parser.add_argument(
            "-y", "--year",
            type=str,
            default=None,
            help="The copyright year to be listed in the license."
        )
        parser.add_argument(
            "-l", "--language",
            type=str,
            default=None,
            help="The language for which the license header should be formatted."
        )
        parser.add_argument(
            "-f", "--file",
            type=str,
            default=None,
            help="The output file name where the license should be saved."
        )
        parser.add_argument(
            "--header",
            action="store_true",
            help="Generate license header format for source files."
        )
        parser.add_argument(
            "--vars",
            action="store_true",
            help="Option to list all template variables for the specified license."
        )

        args = parser.parse_args()
    
    # Handle the case where only --vars is used without a license type
    if args.vars and not args.license:
        print("Error: --vars requires a license type to be specified.")
        # Re-create parser to print help correctly if we are in the CLI path
        if args is None:
            parser = argparse.ArgumentParser(description="Lice License Generator: Automates the creation of open-source license files.")
            parser.add_argument("license", type=str, nargs='?', help="The type of license to generate (e.g., mit, gpl3, bsd3).")
            parser.add_argument("-o", "--org", type=str, default=None, help="The organization under which the license is registered.")
            parser.add_argument("-p", "--proj", type=str, default=None, help="The project name for which the license is generated.")
            parser.add_argument("-t", "--template", type=str, default=None, help="The path to a custom license template file.")
            parser.add_argument("-y", "--year", type=str, default=None, help="The copyright year to be listed in the license.")
            parser.add_argument("-l", "--language", type=str, default=None, help="The language for which the license header should be formatted.")
            parser.add_argument("-f", "--file", type=str, default=None, help="The output file name where the license should be saved.")
            parser.add_argument("--header", action="store_true", help="Generate license header format for source files.")
            parser.add_argument("--vars", action="store_true", help="Option to list all template variables for the specified license.")
            parser.print_help()
            sys.exit(1)

    # Delegate to core.main
    core_main(args)

if __name__ == "__main__":
    # When run directly, we must parse arguments normally
    parser = argparse.ArgumentParser(
        description="Lice License Generator: Automates the creation of open-source license files."
    )
    parser.add_argument(
        "license",
        type=str,
        nargs='?',  # Makes it optional if we only want to run --vars or similar
        help="The type of license to generate (e.g., mit, gpl3, bsd3)."
    )
    parser.add_argument(
        "-o", "--org",
        type=str,
        default=None,
        help="The organization under which the license is registered."
    )
    parser.add_argument(
        "-p", "--proj",
        type=str,
        default=None,
        help="The project name for which the license is generated."
    )
    parser.add_argument(
        "-t", "--template",
        type=str,
        default=None,
        help="The path to a custom license template file."
    )
    parser.add_argument(
        "-y", "--year",
        type=str,
        default=None,
        help="The copyright year to be listed in the license."
    )
    parser.add_argument(
        "-l", "--language",
        type=str,
        default=None,
        help="The language for which the license header should be formatted."
    )
    parser.add_argument(
        "-f", "--file",
        type=str,
        default=None,
        help="The output file name where the license should be saved."
    )
    parser.add_argument(
        "--header",
        action="store_true",
        help="Generate license header format for source files."
    )
    parser.add_argument(
        "--vars",
        action="store_true",
        help="Option to list all template variables for the specified license."
    )
    
    args = parser.parse_args()
    
    # Handle the case where only --vars is used without a license type
    if args.vars and not args.license:
        print("Error: --vars requires a license type to be specified.")
        parser.print_help()
        sys.exit(1)

    # Delegate to core.main
    core_main(args)
