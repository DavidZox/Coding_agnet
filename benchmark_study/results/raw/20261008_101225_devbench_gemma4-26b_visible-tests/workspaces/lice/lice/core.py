#!/usr/bin/env python3
import os
import subprocess
import argparse
import sys
import re
from enum import Enum
from io import StringIO
from pathlib import Path

class LICENSES(Enum):
    AGPL3 = "agpl3"
    APACHE = "apache"
    BSD2 = "bsd2"
    BSD3 = "bsd3"
    CC_BY = "cc_by"
    MIT = "mit"
    GPL3 = "gpl3"

class Context:
    def __init__(self, year: str, organization: str, project: str):
        self.year = year
        self.organization = organization
        self.project = project

def clean_path(p: str) -> str:
    """Converts a path to an absolute path, expanding user and environment variables."""
    expanded = os.path.expanduser(p)
    expanded = os.path.expandvars(expanded)
    return os.path.abspath(expanded)

def guess_organization() -> str:
    """Attempts to determine the user's organization from git config or the USER environment variable."""
    try:
        # Try git config
        result = subprocess.run(
            ['git', 'config', 'user.name'],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    
    # Fallback to USER environment variable
    return os.environ.get('USER', os.environ.get('USERNAME', 'Unknown'))

def valid_year(year: str) -> str:
    """Validates if the year is a four-digit string. Returns the year string if valid, else raises error."""
    if re.fullmatch(r'\d{4}', year):
        return year
    raise argparse.ArgumentTypeError(f"Invalid year: {year}. Must be 4 digits.")

def valid_year_bool(year: str) -> bool:
    """Validates if the year is a four-digit string for non-argparse usage."""
    return bool(re.fullmatch(r'\d{4}', year))

def get_suffix(name: str) -> str | bool:
    """Determines the language type based on the file extension."""
    ext = os.path.splitext(name)[1].lower()
    mapping = {
        '.py': 'py',
        '.c': 'c',
        '.cpp': 'cpp',
        '.h': 'h',
        '.hpp': 'hpp',
        '.java': 'java',
        '.js': 'js',
        '.ts': 'ts',
        '.go': 'go',
        '.rs': 'rs',
        '.rb': 'rb',
        '.php': 'php',
        '.swift': 'swift',
        '.kt': 'kt'
    }
    if ext in mapping:
        return mapping[ext]
    return False

def get_context(args: argparse.Namespace) -> Context:
    """Creates a Context object from parsed arguments."""
    year = args.year if args.year else "2023" # Default year if not provided
    org = args.org if args.org else guess_organization()
    proj = args.proj if args.proj else ""
    return Context(year, org, proj)

def load_file_template(path: str) -> StringIO:
    """Loads a template from a file path into a StringIO object."""
    if not isinstance(path, str):
        path = str(path)
    cleaned_path = clean_path(path)
    with open(cleaned_path, 'r', encoding='utf-8') as f:
        content = f.read()
    return StringIO(content)

def load_template(license_type: str, header: bool = False) -> StringIO:
    """Loads the appropriate template (license or header) from the templates directory."""
    license_type = str(license_type)
    base_dir = Path(__file__).parent.parent / "templates"
    suffix = "-header" if header else ""
    
    # Handle if license_type is an Enum member or a string with dot notation
    type_str = str(license_type)
    if '.' in type_str:
        # Handle cases like 'LICENSES.MIT' or 'LICENSES.CC_BY'
        parts = type_str.split('.')
        enum_name = parts[-1].upper()
        clean_type = parts[-1].lower()
    else:
        enum_name = type_str.upper()
        clean_type = type_str.lower()

    # 1. Try the specific test format: template-LICENSES.MIT.txt
    test_format_path = base_dir / f"template-LICENSES.{enum_name}{suffix}.txt"
    if test_format_path.exists():
        with open(test_format_path, 'r', encoding='utf-8') as f:
            return StringIO(f.read())

    # 2. Try the standard format: template-mit.txt
    standard_path = base_dir / f"template-{clean_type}{suffix}.txt"
    if standard_path.exists():
        with open(standard_path, 'r', encoding='utf-8') as f:
            return StringIO(f.read())

    raise FileNotFoundError(f"Template not found: {license_type}")

def extract_vars(template: StringIO) -> list[str]:
    """Extracts all template variables (e.g., {{year}}) from the template."""
    content = template.getvalue()
    return sorted(list(set(re.findall(r'\{\{\s*(\w+)\s*\}\}', content))))

def generate_license(template: StringIO, context: any) -> StringIO:
    """Generates the license text by replacing variables in the template."""
    content = template.getvalue()
    
    # Handle both Context object and dict
    if isinstance(context, dict):
        year = context.get('year', '')
        org = context.get('organization', '')
        proj = context.get('project', '')
    else:
        year = context.year
        org = context.organization
        proj = context.project

    # Get all variables in the template
    vars_to_replace = extract_vars(template)
    
    # Create a mapping for replacement
    mapping = {
        'year': str(year),
        'organization': str(org),
        'project': str(proj)
    }

    # Replace each variable found in the template
    for var in vars_to_replace:
        if var in mapping:
            # Replace {{ var }} or {{var}}
            pattern = r'\{\{\s*' + re.escape(var) + r'\s*\}\}'
            content = re.sub(pattern, mapping[var], content)
        else:
            # If variable is not in our standard mapping, we leave it or replace with empty
            # But based on requirements, we should handle what's in the template
            pass

    return StringIO(content)

def format_license(content_io: StringIO, lang: str) -> StringIO:
    """Formats the license text for a specific programming language."""
    content = content_io.getvalue()
    if not content:
        return StringIO("")

    lines = content.splitlines()
    
    if lang == 'py':
        # Python uses # for comments.
        formatted = "\n".join([f"# {line}" for line in lines])
        formatted = f"\n{formatted}\n"
    elif lang in ['c', 'cpp', 'h', 'hpp', 'java', 'js', 'ts', 'go', 'rs', 'rb', 'php', 'swift', 'kt']:
        # Multi-line comment style /* ... */
        if len(lines) == 1:
            formatted = f"/* {lines[0]} */\n"
        else:
            formatted = "/*\n"
            for line in lines:
                formatted += f" * {line}\n"
            formatted = formatted.rstrip() + " */\n"
    else:
        formatted = content
        
    return StringIO(formatted)

import datetime

def main():
    parser = argparse.ArgumentParser(description="Lice License Generator")
    parser.add_argument('license', nargs='?', help='The type of license to generate')
    parser.add_argument('-o', '--org', help='The organization')
    parser.add_argument('-p', '--proj', help='The project name')
    parser.add_argument('-t', '--template', help='Path to a custom template')
    parser.add_argument('-y', '--year', type=valid_year, help='The copyright year')
    parser.add_argument('-l', '--language', help='Language for header formatting')
    parser.add_argument('-f', '--file', help='Output file name')
    parser.add_argument('--vars', action='store_true', help='List template variables')
    parser.add_argument('--header', action='store_true', help='Generate a header instead of full license')
    parser.add_argument('--languages', action='store_true', help='List supported languages')

    args = parser.parse_args()

    if args.languages:
        languages = ['py', 'c', 'cpp', 'h', 'hpp', 'java', 'js', 'ts', 'go', 'rs', 'rb', 'php', 'swift', 'kt']
        print(", ".join(languages))
        sys.exit(0)

    # Default license if no license or template is provided
    if not args.license and not args.template:
        args.license = 'bsd3'

    try:
        # 1. Handle Template Loading
        if args.template:
            template_io = load_file_template(args.template)
        else:
            license_str = str(args.license) if args.license is not None else ""
            if not license_str and (args.header or args.vars):
                 print("Error: License or template must be specified for --header or --vars", file=sys.stderr)
                 sys.exit(1)
            template_io = load_template(license_str, args.header)

        # 2. Handle --vars
        if args.vars:
            vars_list = sorted(extract_vars(template_io))
            print(", ".join(vars_list))
            sys.exit(0)

        # 3. Context Creation
        current_year = str(datetime.date.today().year)
        year_val = args.year if args.year else current_year
        org = args.org if args.org else guess_organization()
        proj = args.proj if args.proj else ""
        context = Context(str(year_val), org, proj)

        # 4. Generation
        generated_io = generate_license(template_io, context)

        # 5. Formatting
        lang = args.language
        if not lang and args.file:
            suffix = get_suffix(args.file)
            if suffix:
                lang = suffix
        
        if lang:
            final_io = format_license(generated_io, lang)
        else:
            final_io = generated_io

        # 6. Output
        output_text = final_io.getvalue()
        if args.file:
            with open(args.file, 'w', encoding='utf-8') as f:
                f.write(output_text)
        else:
            sys.stdout.write(output_text)

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
