import argparse
import os
import subprocess
import sys
from io import StringIO
from typing import List, Union

class Context:
    def __init__(self, year: str, organization: str, project: str):
        self.year = year
        self.organization = organization
        self.project = project

def clean_path(p: str) -> str:
    return os.path.normpath(p)

def guess_organization() -> str:
    # Try git config
    try:
        org = subprocess.check_output(['git', 'config', 'user.name'], stderr=subprocess.DEVNULL).decode().strip()
        if org:
            return org
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    
    # Try $USER environment variable
    return os.environ.get('USER', os.environ.get('USERNAME', ''))

def get_context(args: argparse.Namespace) -> Context:
    year = args.year if args.year else ""
    org = args.org if args.org else guess_organization()
    proj = args.proj if args.proj else ""
    return Context(year, org, proj)

def load_file_template(path: str) -> StringIO:
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    return StringIO(content)

def load_template(license_type: str, header: bool = False) -> StringIO:
    # Mapping license type to template filename
    # Based on PRD: template-afl3.txt, template-apache.txt, etc.
    # Header templates: template-agpl3-header.txt
    base_name = license_type.lower()
    
    if header:
        filename = f"templates/template-{base_name}-header.txt"
    else:
        filename = f"templates/template-{base_name}.txt"
    
    # Fallback for common naming if exact match fails (e.g., bsd3 vs bsd-3)
    if not os.path.exists(filename):
        # Try common variations if needed, but following PRD strictly
        pass

    return load_file_template(filename)

def extract_vars(template: StringIO) -> List[str]:
    template.seek(0)
    content = template.read()
    import re
    # Find all patterns like {{ variable }}
    return re.findall(r'\{\{\s*(\w+)\s*\}\}', content)

def generate_license(template: StringIO, context: Context) -> StringIO:
    template.seek(0)
    content = template.read()
    
    # Replace variables
    content = content.replace('{{ year }}', context.year)
    content = content.replace('{{ organization }}', context.organization)
    content = content.replace('{{ project }}', context.project)
    
    return StringIO(content)

def format_license(content_io: StringIO, lang: str) -> StringIO:
    content_io.seek(0)
    lines = content_io.readlines()
    
    formatted_lines = []
    if lang == 'py':
        for line in lines:
            formatted_lines.append(f"# {line.strip()}\n")
    elif lang == 'js' or lang == 'ts':
        for line in lines:
            formatted_lines.append(f"/* {line.strip()} */\n")
    elif lang == 'c' or lang == 'cpp':
        for line in lines:
            formatted_lines.append(f" * {line.strip()}\n")
        # Wrap in block comment if needed, but simple line prefix is common
    else:
        # Default: just return as is
        formatted_lines = lines

    return StringIO("".join(formatted_lines))

def get_suffix(name: str) -> Union[str, bool]:
    if '.' in name:
        return name.split('.')[-1]
    return False

def main():
    parser = argparse.ArgumentParser(description="Lice License Generator")
    parser.add_argument('license', nargs='?', help='The type of license to generate')
    parser.add_argument('-o', '--org', help='The organization under which the license is registered')
    parser.add_argument('-p', '--proj', help='The project name')
    parser.add_argument('-t', '--template', help='The path to a custom license template file')
    parser.add_argument('-y', '--year', help='The copyright year')
    parser.add_argument('-l', '--language', help='The language for which the license header should be formatted')
    parser.add_argument('-f', '--file', help='The output file name')
    parser.add_argument('--vars', action='store_true', help='List all template variables')
    parser.add_argument('--header', action='store_true', help='Generate a header instead of a full license')

    args = parser.parse_args()

    if not args.license and not args.template and not args.header:
        parser.print_help()
        return

    # Handle custom template or standard template
    if args.template:
        template_io = load_file_template(clean_path(args.template))
    elif args.license:
        template_io = load_template(args.license, args.header)
    else:
        # If only --header or --vars is called without license, it's an error in this logic
        # but we follow the flow
        return

    if args.vars:
        vars_list = extract_vars(template_io)
        for v in vars_list:
            print(v)
        return

    context = get_context(args)
    
    # Generate content
    generated_io = generate_license(template_io, context)
    
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
        sys.stdout.write(output)

if __name__ == "__main__":
    main()
