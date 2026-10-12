import os
import subprocess
import re
import argparse
import sys
import time
from typing import Union, List
from io import StringIO
from enum import Enum

class LICENSES(Enum):
    AGPL3 = "agpl3"
    Apache = "apache"
    BSD2 = "bsd2"
    BSD3 = "bsd3"
    # Additional licenses will be added as needed

    def __str__(self):
        return self.value

class Context:
    """
    Represents the context for license generation.
    """
    def __init__(self, year: str, organization: str, project: str):
        self.year = year
        self.organization = organization
        self.project = project

def clean_path(p: str) -> str:
    """
    Handles path expansion (e.g., ~ or $USER).
    """
    return os.path.abspath(os.path.expanduser(os.path.expandvars(p)))

def valid_year(year: str) -> str:
    """
    Validates if the year is a four-digit number.
    Returns the year string if valid, otherwise raises argparse.ArgumentTypeError.
    """
    if not re.fullmatch(r'\d{4}', year):
        raise argparse.ArgumentTypeError(f"Invalid year: {year}. Year must be a four-digit number.")
    return year

def get_suffix(name: str) -> Union[str, bool]:
    """
    Determines the language suffix based on the file extension.
    Returns the suffix string or False if no extension is found.
    """
    known_suffixes = {'py', 'c', 'cpp', 'h', 'java', 'js', 'ts', 'go', 'rs', 'rb', 'php', 'sh', 'html', 'css'}
    if '.' not in name:
        return False
    suffix = os.path.splitext(name)[1].lstrip('.')
    if not suffix or suffix not in known_suffixes:
        return False
    return suffix

def guess_organization() -> str:
    """
    Attempts to determine the user's organization from git config or the USER environment variable.
    """
    # Try git config first
    try:
        org = subprocess.check_output(
            ['git', 'config', 'user.name'], 
            stderr=subprocess.DEVNULL, 
            text=True
        ).strip()
        if org:
            return org
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Fallback to USER environment variable
    return os.environ.get('USER', os.environ.get('USERNAME', ''))

# Placeholder functions for future implementation as per UML/Architecture
def get_context(args) -> Context:
    year = args.year if args.year else str(time.localtime().tm_year)
    org = args.org if args.org else guess_organization()
    proj = args.proj if args.proj else ""
    return Context(year, org, proj)

def load_file_template(path: str) -> StringIO:
    """
    Reads a template file from the specified path.
    """
    if not os.path.exists(path):
        raise ValueError(f"path does not exist: {path}")
    with open(path, 'r') as f:
        content = f.read()
    sio = StringIO()
    sio.write(str(content))
    sio.seek(0)
    return sio

def load_template(license: str, header: bool = False) -> StringIO:
    """
    Loads the corresponding template based on the license name and whether it's a header.
    """
    if isinstance(license, Enum):
        license_val = license.value
    else:
        license_val = str(license).lower()

    template_name = f"template-{license_val}"
    if header:
        template_name += "-header"
    
    # Get the absolute path to the templates directory relative to this file
    # Using os.path.join with multiple components to ensure robust path resolution
    current_dir = os.path.dirname(os.path.abspath(__file__))
    templates_dir = os.path.join(current_dir, "..", "templates")
    template_path = os.path.join(templates_dir, f"{template_name}.txt")
    
    try:
        return load_file_template(template_path)
    except ValueError:
        if header:
            # If it's a header template and not found, return an empty StringIO as per test requirements
            return StringIO()
        raise

def extract_vars(template: StringIO) -> List[str]:
    """
    Extracts all variables in {{variable}} format from the template.
    """
    content = template.getvalue()
    template.seek(0)
    matches = re.finditer(r'\{\{(.*?)\}\}', content)
    vars_list = []
    for m in matches:
        var = m.group(1).strip()
        if var not in vars_list:
            vars_list.append(var)
    return sorted(vars_list)

def generate_license(template: StringIO, context: Union[Context, dict]) -> StringIO:
    """
    Generates the license text by filling in the template with context information.
    """
    content = template.getvalue()
    template.seek(0)
    
    if isinstance(context, dict):
        replacements = {
            "year": context.get("year", ""),
            "organization": context.get("organization", ""),
            "project": context.get("project", "")
        }
    else:
        replacements = {
            "year": context.year,
            "organization": context.organization,
            "project": context.project
        }
    
    # Use regex to replace {{ var }} or {{var}}
    for var, value in replacements.items():
        pattern = r'\{\{\s*' + re.escape(var) + r'\s*\}\}'
        content = re.sub(pattern, str(value), content)
    
    sio = StringIO()
    sio.write(content)
    sio.seek(0)
    return sio

def format_license(template: StringIO, lang: str) -> StringIO:
    """
    Formats the license text for a specific programming language comment style.
    """
    content = template.getvalue()
    if not content:
        return template

    lines = content.splitlines()
    formatted_lines = []

    if lang == 'py':
        # Python uses # for comments.
        for line in lines:
            formatted_lines.append(f"# {line}")
        output = "\n".join(formatted_lines)
        # Ensure it starts and ends with a newline if needed by tests
        if not output.startswith('\n'):
            output = '\n' + output
        if not output.endswith('\n'):
            output = output + '\n'
    elif lang in ['c', 'cpp', 'h']:
        # C-style block comments
        output = "/*\n"
        for line in lines:
            if line.strip():
                output += f" * {line}\n"
            else:
                output += " *\n"
        output = output.rstrip('\n') + " */\n"
    else:
        # Default fallback
        output = "\n".join(lines)

    sio = StringIO()
    sio.write(output)
    sio.seek(0)
    return sio

def main():
    # Entry point for the CLI
    parser = argparse.ArgumentParser(description="Lice License Generator")
    parser.add_argument('license', nargs='?', default='bsd3', help='The type of license to generate.')
    parser.add_argument('-o', '--org', help='The organization under which the license is registered.')
    parser.add_argument('-p', '--proj', help='The project name for which the license is generated.')
    parser.add_argument('-t', '--template', help='The path to a custom license template file.')
    parser.add_argument('-y', '--year', type=valid_year, help='The copyright year to be listed in the license.')
    parser.add_argument('-l', '--language', help='The language for which the license header should be formatted.')
    parser.add_argument('-f', '--file', help='The output file name where the license should be saved.')
    parser.add_argument('--vars', action='store_true', help='Option to list all template variables for the specified license.')
    parser.add_argument('--languages', action='store_true', help='List supported languages.')

    args = parser.parse_args()

    if args.languages:
        languages = ['py', 'c', 'cpp', 'h', 'java', 'js', 'ts', 'go', 'rs', 'rb', 'php', 'sh', 'html', 'css']
        for lang in languages:
            print(lang)
        sys.exit(0)

    if args.vars:
        if not args.license:
            parser.print_help()
            sys.exit(1)
        try:
            # Try to find the license in LICENSES enum
            lic_enum = next((l for l in LICENSES if l.value == args.license.lower()), None)
            if lic_enum:
                template = load_template(lic_enum)
            elif args.template:
                template = load_file_template(clean_path(args.template))
            else:
                # If not in enum, we assume it's a valid license name for template lookup
                template = load_template(args.license)
            
            vars_list = extract_vars(template)
            
            if args.template:
                print(f"The custom template contains the following variables:")
            else:
                # Use the provided license name or the enum name
                lic_name = args.license.lower()
                if lic_enum:
                    lic_name = lic_enum.name.lower()
                print(f"The {lic_name} license template contains the following variables:")
            
            for v in vars_list:
                print(v)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
        except (FileNotFoundError, ValueError):
            print(f"Error: Template file not found.")
            sys.exit(1)
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
        sys.exit(0)

    if not args.license and not args.template:
        # This case is technically unreachable now due to default='bsd3'
        # but kept for logical completeness if default is removed.
        parser.print_help()
        return

    try:
        if args.template:
            template = load_file_template(clean_path(args.template))
        else:
            if not args.license:
                parser.print_help()
                sys.exit(1)
            template = load_template(args.license, header=bool(args.language))

        context = get_context(args)
        
        generated_sio = generate_license(template, context)
        
        if args.language:
            final_sio = format_license(generated_sio, args.language)
        else:
            final_sio = generated_sio

        output = final_sio.getvalue()

        if args.file:
            with open(args.file, 'w') as f:
                f.write(output)
        else:
            print(output, end='')
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except (FileNotFoundError, ValueError):
        print(f"Error: Template file not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
