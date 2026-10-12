import os
import subprocess
import re
import argparse
from io import StringIO
from typing import List, Union

class Context:
    def __init__(self, year: str, organization: str, project: str):
        self._year = year
        self._organization = organization
        self._project = project

    @property
    def year(self) -> str:
        return self._year

    @property
    def organization(self) -> str:
        return self._organization

    @property
    def project(self) -> str:
        return self._project

def clean_path(p: str) -> str:
    """Cleans the path string."""
    return os.path.normpath(p)

def guess_organization() -> str:
    """Attempts to determine the user's organization from git config or the USER environment variable."""
    try:
        # Try git config user.name
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

    # Fallback to $USER environment variable
    return os.environ.get('USER', os.environ.get('USERNAME', 'Unknown'))

def get_suffix(name: str) -> Union[str, bool]:
    """Determines the file suffix."""
    _, ext = os.path.splitext(name)
    return ext if ext else False

def load_file_template(path: str) -> StringIO:
    """Reads a template file from the specified path and returns a StringIO object."""
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    return StringIO(content)

def load_template(license: str, header: bool = False) -> StringIO:
    """
    Loads a template based on the license name and whether it's a header.
    Templates are expected to be in the 'templates/' directory.
    """
    # Normalize license name (e.g., 'mit' -> 'mit')
    license_name = license.lower()
    
    if header:
        template_name = f"template-{license_name}-header.txt"
    else:
        template_name = f"template-{license_name}.txt"
    
    # Assuming templates directory is at the project root or relative to this file
    # For the purpose of this implementation, we look in a 'templates' folder in the current working directory
    template_path = os.path.join('templates', template_name)
    
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template file not found: {template_path}")
        
    return load_file_template(template_path)

def extract_vars(template: StringIO) -> List[str]:
    """Extracts all variables in {{ variable }} format from the template."""
    template.seek(0)
    content = template.read()
    return re.findall(r'\{\{\s*(\w+)\s*\}\}', content)

def generate_license(template: StringIO, context: Context) -> StringIO:
    """Generates the license text by replacing template variables with context values."""
    template.seek(0)
    content = template.read()
    
    replacements = {
        'year': context.year,
        'organization': context.organization,
        'project': context.project
    }
    
    for var, val in replacements.items():
        content = re.sub(r'\{\{\s*' + var + r'\s*\}\}', val, content)
        
    return StringIO(content)

def format_license(content: StringIO, lang: str) -> StringIO:
    """Formats the license text according to the specified programming language comment style."""
    content.seek(0)
    lines = content.readlines()
    
    if lang == 'py':
        comment_prefix = '# '
    elif lang in ['js', 'cpp', 'c', 'java']:
        comment_prefix = '// '
    elif lang in ['sh', 'bash', 'yaml']:
        comment_prefix = '# '
    elif lang == 'html':
        # HTML is a special case, but for simplicity in this task we'll handle basic comment styles
        return content 
    else:
        # Default to no prefix if language is unknown
        return content

    formatted_lines = [f"{comment_prefix}{line.rstrip()}" if line.strip() else line for line in lines]
    return StringIO("".join(formatted_lines))

def get_context(args: argparse.Namespace) -> Context:
    """Creates a Context object based on the parsed arguments."""
    year = args.year if args.year else ""
    org = args.org if args.org else guess_organization()
    proj = args.proj if args.proj else ""
    return Context(year=year, organization=org, project=proj)

def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(description="Lice License Generator")
    parser.add_argument('license', nargs='?', help='The type of license to generate.')
    parser.add_argument('-o', '--org', help='The organization under which the license is registered.')
    parser.add_argument('-p', '--proj', help='The project name for which the license is generated.')
    parser.add_argument('-t', '--template', help='The path to a custom license template file.')
    parser.add_argument('-y', '--year', help='The copyright year to be listed in the license.')
    parser.add_argument('-l', '--language', help='The language for which the license header should be formatted.')
    parser.add_argument('-f', '--file', help='The output file name where the license should be saved.')
    parser.add_argument('--header', action='store_true', help='Generate a license header.')
    parser.add_argument('--vars', action='store_true', help='List all template variables for the specified license.')

    args = parser.parse_args()

    if not args.license and not args.template and not args.header and not args.vars:
        # If no license is provided but other flags are, we might need a license to find a template
        # However, based on usage, license is usually positional.
        pass

    # Handle --vars
    if args.vars:
        if not args.license:
            parser.error("the following arguments are required: license")
        if args.template:
            template_io = load_file_template(args.template)
        else:
            template_io = load_template(args.license, header=args.header)
        variables = extract_vars(template_io)
        for var in variables:
            print(var)
        return

    # Handle license generation
    if not args.license and not args.template:
        # If no license/template provided, we can't proceed
        # But if --header is used without license, it's ambiguous. 
        # For this implementation, we assume license is required for generation.
        if not args.header:
            parser.print_help()
            return

    try:
        if args.template:
            template_io = load_file_template(args.template)
        else:
            if not args.license:
                parser.error("the following arguments are required: license")
            template_io = load_template(args.license, header=args.header)

        context = get_context(args)
        
        # Generate content
        content_io = generate_license(template_io, context)
        
        # Format if language is specified
        if args.language:
            content_io = format_license(content_io, args.language)
        
        result = content_io.getvalue()

        # Output
        if args.file:
            with open(args.file, 'w', encoding='utf-8') as f:
                f.write(result)
        else:
            print(result, end='')

    except Exception as e:
        print(f"Error: {e}")
        exit(1)

if __name__ == "__main__":
    main()
