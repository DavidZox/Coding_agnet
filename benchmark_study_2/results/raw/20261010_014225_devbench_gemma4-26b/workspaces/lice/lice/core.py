import argparse
import os
import subprocess
import sys
import re
from io import StringIO
from datetime import datetime
from pathlib import Path

class Context:
    def __init__(self, year, organization, project):
        self.year = year
        self.organization = organization
        self.project = project

def clean_path(p):
    return os.path.normpath(p)

def guess_organization():
    # Try git config
    try:
        org = subprocess.check_output(['git', 'config', 'user.name'], stderr=subprocess.DEVNULL, text=True).strip()
        if org:
            return org
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    
    # Try $USER environment variable
    return os.environ.get('USER') or os.environ.get('USERNAME') or "Unknown"

def load_file_template(path):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    s = StringIO()
    s.write(content)
    s.seek(0)
    return s

def load_template(license_name, header=False):
    # The templates are in a directory named 'templates' relative to the project root or current dir
    # Based on architecture, templates/ is at the root.
    base_dir = Path(__file__).parent.parent / "templates"
    
    if header:
        filename = f"template-{license_name.lower()}-header.txt"
    else:
        filename = f"template-{license_name.lower()}.txt"
    
    template_path = base_dir / filename
    
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")
        
    return load_file_template(str(template_path))

def extract_vars(template_sio):
    template_sio.seek(0)
    content = template_sio.read()
    # Find all {{variable_name}}
    vars_found = re.findall(r'\{\{\s*(\w+)\s*\}\}', content)
    return sorted(list(set(vars_found)))

def generate_license(template_sio, context):
    template_sio.seek(0)
    content = template_sio.read()
    
    # Replace variables using {{ variable }} format
    content = re.sub(r'\{\{\s*year\s*\}\}', str(context.year), content)
    content = re.sub(r'\{\{\s*organization\s*\}\}', str(context.organization), content)
    content = re.sub(r'\{\{\s*project\s*\}\}', str(context.project), content)
    
    s = StringIO()
    s.write(content)
    s.seek(0)
    return s

def format_license(content_sio, lang):
    content_sio.seek(0)
    content = content_sio.getvalue()
    
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
    elif lang == 'c' or lang == 'cpp' or lang == 'h':
        for line in lines:
            formatted_lines.append(f" * {line}")
        formatted_lines.insert(0, "/*")
        formatted_lines.append(" */")
    else:
        # Default: just return as is
        return content_sio

    s = StringIO()
    s.write("\n".join(formatted_lines))
    s.seek(0)
    return s

def get_suffix(name):
    # If name is a file path, return extension without dot
    ext = os.path.splitext(name)[1]
    if ext:
        return ext[1:]
    return None

def get_context(args):
    year = args.year if args.year else str(datetime.now().year)
    org = args.org if args.org else guess_organization()
    proj = args.proj if args.proj else ""
    return Context(year, org, proj)

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
    parser.add_argument('--header', action='store_true', help='Generate a header instead of full license')

    args = parser.parse_args()

    # If no license is provided, it might be a general call, but PRD implies license is required for generation
    if not args.license and not args.template and not args.language:
        # This handles the 'lice' command without args if needed, though usually it needs a license
        return

    try:
        if args.vars:
            # For --vars, we need to know which template to look at
            if args.template:
                template_sio = load_file_template(args.template)
            elif args.license:
                template_sio = load_template(args.license, header=False)
            else:
                print("Error: --vars requires a license or a template path.")
                sys.exit(1)
            
            variables = extract_vars(template_sio)
            print(", ".join(variables))
            return

        # Determine template
        if args.template:
            template_sio = load_file_template(args.template)
        elif args.license:
            template_sio = load_template(args.license, header=args.header)
        else:
            # If only language is provided, we might be trying to format an existing file? 
            # But the usage shows 'python lice/core.py apache --header --language py'
            # So we assume license is required if we are generating.
            print("Error: License type must be specified.")
            sys.exit(1)

        context = get_context(args)
        
        # Generate
        content_sio = generate_license(template_sio, context)
        
        # Format
        if args.language:
            content_sio = format_license(content_sio, args.language)
        
        output = content_sio.getvalue()

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
