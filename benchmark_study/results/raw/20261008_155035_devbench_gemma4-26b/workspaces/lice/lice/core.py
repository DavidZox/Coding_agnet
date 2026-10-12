import argparse
import os
import re
import subprocess
from io import StringIO
from datetime import datetime
from typing import List, Union

class Context:
    def __init__(self, year: str, organization: str, project: str):
        self.year = year
        self.organization = organization
        self.project = project

def clean_path(p: str) -> str:
    return os.path.normpath(p)

def get_suffix(name: str) -> Union[str, bool]:
    _, ext = os.path.splitext(name)
    return ext if ext else True

def guess_organization() -> str:
    try:
        # Try git config user.name
        org = subprocess.check_output(
            ['git', 'config', 'user.name'], 
            stderr=subprocess.DEVNULL, 
            text=True
        ).strip()
        if org:
            return org
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    
    return os.environ.get('USER', os.environ.get('USERNAME', 'Unknown'))

def load_file_template(path: str) -> StringIO:
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    return StringIO(content)

def load_template(license_type: str, header: bool = False) -> StringIO:
    suffix = "-header" if header else ""
    filename = f"template-{license_type.lower()}{suffix}.txt"
    # Assuming templates folder is in the same directory as the project root
    # or relative to the execution context. Based on architecture, it's in ./templates
    path = os.path.join('templates', filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Template not found: {path}")
    return load_file_template(path)

def extract_vars(template: StringIO) -> List[str]:
    template.seek(0)
    content = template.read()
    # Find all patterns like {{variable}}
    vars_found = re.findall(r'\{\{\s*(.*?)\s*\}\}', content)
    return sorted(list(set(vars_found)))

def generate_license(template: StringIO, context: Context) -> StringIO:
    template.seek(0)
    content = template.read()
    
    replacements = {
        'year': context.year,
        'organization': context.organization,
        'project': context.project
    }
    
    for var, val in replacements.items():
        # Use regex to replace {{ var }} or {{var}} or {{  var  }}
        pattern = re.compile(r'\{\{\s*' + re.escape(var) + r'\s*\}\}')
        content = pattern.sub(val, content)
    
    return StringIO(content)

def format_license(template: StringIO, lang: str) -> StringIO:
    template.seek(0)
    content = template.read()
    lines = content.splitlines()
    
    formatted_lines = []
    if lang == 'py':
        for line in lines:
            formatted_lines.append(f"# {line}")
    elif lang == 'js' or lang == 'ts':
        for line in lines:
            formatted_lines.append(f" * {line}")
        formatted_lines.insert(0, "/*")
        formatted_lines.append(" */")
    elif lang == 'cpp' or lang == 'c':
        for line in lines:
            formatted_lines.append(f" * {line}")
        formatted_lines.insert(0, "/*")
        formatted_lines.append(" */")
    elif lang == 'sh' or lang == 'bash':
        for line in lines:
            formatted_lines.append(f"# {line}")
    else:
        # Default fallback
        formatted_lines = lines
        
    return StringIO("\n".join(formatted_lines))

def get_context(args: argparse.Namespace) -> Context:
    year = args.year if args.year else str(datetime.now().year)
    org = args.org if args.org else guess_organization()
    proj = args.proj if args.proj else ""
    return Context(year, org, proj)

def main():
    parser = argparse.ArgumentParser(description="Lice License Generator")
    parser.add_argument('license', nargs='?', help='The type of license to generate')
    parser.add_argument('-o', '--org', help='The organization under which the license is registered')
    parser.add_argument('-p', '--proj', help='The project name')
    parser.add_argument('-t', '--template', help='Path to a custom license template file')
    parser.add_argument('-y', '--year', help='The copyright year')
    parser.add_argument('-l', '--language', help='The language for the license header')
    parser.add_argument('-f', '--file', help='The output file name')
    parser.add_argument('--vars', action='store_true', help='List all template variables')
    parser.add_argument('--header', action='store_true', help='Generate a license header')

    args = parser.parse_args()

    if args.vars:
        if not args.license:
            print("Error: --vars requires a license type.")
            return
        try:
            template = load_template(args.license)
            variables = extract_vars(template)
            print(", ".join(variables))
        except Exception as e:
            print(f"Error: {e}")
        return

    if not args.license and not args.language:
        parser.print_help()
        return

    try:
        # Determine if we are generating a header or a full license
        is_header = args.header or args.language is not None
        
        if args.template:
            template = load_file_template(args.template)
        elif args.license:
            template = load_template(args.license, header=is_header)
        else:
            # If no license provided but language is, we might be formatting an existing file?
            # But the PRD implies 'lice -l py' is for header generation.
            # However, the usage shows 'python lice/core.py apache --header --language py'
            # If user just does 'python lice/core.py -l py', it's ambiguous.
            # Let's assume if license is missing, we can't generate.
            print("Error: License type must be specified.")
            return

        context = get_context(args)
        
        # Generate content
        content_io = generate_license(template, context)
        
        # Format if language is specified
        if args.language:
            content_io = format_license(content_io, args.language)
        
        output = content_io.getvalue()

        if args.file:
            with open(args.file, 'w', encoding='utf-8') as f:
                f.write(output)
        else:
            print(output)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
