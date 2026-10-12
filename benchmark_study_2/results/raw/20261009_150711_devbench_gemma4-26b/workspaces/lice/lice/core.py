import os
import sys
import argparse
import subprocess
import re
import datetime
from io import StringIO
from typing import List, Union

class Context:
    def __init__(self, year, organization, project):
        self._year = year
        self._organization = organization
        self._project = project

    @property
    def year(self):
        return self._year

    @property
    def organization(self):
        return self._organization

    @property
    def project(self):
        return self._project

def clean_path(p: str) -> str:
    """Cleans the provided path string."""
    return os.path.normpath(p)

def guess_organization() -> str:
    """Attempts to determine the user's organization from git config or the USER environment variable."""
    try:
        # Try git config user.name
        org = subprocess.check_output(['git', 'config', 'user.name'], stderr=subprocess.DEVNULL, text=True).strip()
        if org:
            return org
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    
    return os.environ.get('USER', 'Unknown')

def get_context(args: argparse.Namespace) -> Context:
    """Creates a Context object from the parsed arguments."""
    if args.year:
        year = str(args.year)
    else:
        year = str(datetime.date.today().year)
        
    organization = args.org if args.org else guess_organization()
    project = args.proj if args.proj else ""
    return Context(year, organization, project)

def load_file_template(path: str) -> StringIO:
    """Loads a template from a specific file path."""
    with open(path, 'r', encoding='utf-8') as f:
        return StringIO(f.read())

def load_template(license_type: str, header: bool = False) -> StringIO:
    """Loads a template based on the license type and whether it's a header."""
    suffix = "-header.txt" if header else ".txt"
    # Mapping common names to template filenames
    # e.g., mit -> template-mit.txt
    filename = f"template-{license_type.lower()}{suffix}"
    
    # Assuming templates are in a directory named 'templates' relative to the project root
    # In this implementation, we look in the 'templates' folder in the current working directory or project root
    template_path = os.path.join('templates', filename)
    
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template not found: {template_path}")
        
    return load_file_template(template_path)

def extract_vars(template: StringIO) -> List[str]:
    """Extracts all template variables (e.g., {{ year }}) from the template."""
    content = template.getvalue()
    return re.findall(r'\{\{\s*(\w+)\s*\}\}', content)

def generate_license(template: StringIO, context: Context) -> StringIO:
    """Generates the license text by replacing variables in the template."""
    content = template.getvalue()
    
    def replace_var(match):
        var_name = match.group(1).lower()
        if var_name == 'year':
            return context.year
        elif var_name == 'organization':
            return context.organization
        elif var_name == 'project':
            return context.project
        return match.group(0)

    content = re.sub(r'\{\{\s*(\w+)\s*\}\}', replace_var, content)
    return StringIO(content)

def format_license(content_io: StringIO, lang: str) -> StringIO:
    """Formats the license text according to the specified programming language."""
    content = content_io.getvalue()
    lines = content.splitlines()
    
    if lang == 'py':
        formatted = "\n".join([f"# {line}" if line.strip() else "#" for line in lines])
    elif lang == 'js' or lang == 'ts':
        formatted = "\n".join([f" * {line}" if line.strip() else " *" for line in lines])
        formatted = "/*\n" + formatted + "\n*/"
    elif lang == 'c' or lang == 'cpp':
        formatted = "\n".join([f" * {line}" if line.strip() else " *" for line in lines])
        formatted = "/*\n" + formatted + "\n*/"
    else:
        formatted = content
        
    return StringIO(formatted)

def main():
    parser = argparse.ArgumentParser(description="Lice License Generator")
    parser.add_argument('license', nargs='?', help='The type of license to generate')
    parser.add_argument('-o', '--org', help='The organization')
    parser.add_argument('-p', '--proj', help='The project name')
    parser.add_argument('-t', '--template', help='Path to a custom template')
    parser.add_argument('-y', '--year', help='The copyright year')
    parser.add_argument('-l', '--language', help='The language for header formatting')
    parser.add_argument('-f', '--file', help='Output file name')
    parser.add_argument('--vars', action='store_true', help='List template variables')
    parser.add_argument('--header', action='store_true', help='Generate a license header')

    args = parser.parse_args()

    if not args.license and not args.template and not args.language:
        parser.print_help()
        return

    try:
        if args.vars and args.license:
            template = load_template(args.license)
            vars_list = extract_vars(template)
            print(", ".join(vars_list))
            return

        if args.template:
            template = load_file_template(args.template)
        elif args.license:
            template = load_template(args.license, header=args.header)
        else:
            return

        context = get_context(args)
        
        # Generate content
        generated_io = generate_license(template, context)
        
        # Format if language is specified
        if args.language:
            final_io = format_license(generated_io, args.language)
        else:
            final_io = generated_io

        output = final_io.getvalue()

        if args.file:
            with open(args.file, 'w', encoding='utf-8') as f:
                f.write(output)
        else:
            print(output)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
