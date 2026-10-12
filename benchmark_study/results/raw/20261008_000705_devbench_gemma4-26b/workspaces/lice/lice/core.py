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
    return str(Path(p).resolve())

def guess_organization():
    # Try git config
    try:
        org = subprocess.check_output(['git', 'config', 'user.name'], stderr=subprocess.DEVNULL, text=True).strip()
        if org:
            return org
    except (subprocess.CalledProcessError, FileNotFoundError, Exception):
        pass
    
    # Try $USER environment variable
    return os.environ.get('USER') or os.environ.get('USERNAME') or ""

def get_context(args):
    year = args.year if args.year else str(datetime.now().year)
    org = args.org if args.org else guess_organization()
    proj = args.proj if args.proj else ""
    return Context(year, org, proj)

def load_file_template(path):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    s = StringIO()
    s.write(content)
    s.seek(0)
    return s

def load_template(license_name, header=False):
    # The template directory is assumed to be in the same level as the lice package or relative to execution
    # Based on architecture, templates/ is in the root.
    template_dir = Path("templates")
    
    if header:
        template_name = f"template-{license_name.lower()}-header.txt"
    else:
        template_name = f"template-{license_name.lower()}.txt"
    
    template_path = template_dir / template_name
    
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")
        
    return load_file_template(str(template_path))

def extract_vars(template_sio):
    template_sio.seek(0)
    content = template_sio.read()
    # Find all { variable_name }
    vars_found = re.findall(r'\{\s*(\w+)\s*\}', content)
    return sorted(list(set(vars_found)))

def generate_license(template_sio, context):
    template_sio.seek(0)
    content = template_sio.read()
    
    # Replace variables using regex to handle { var } or {var} or { var }
    # The instruction says: "將模板中的變數（如 {year}, {organization}, {project}）替換為 context 中的值。"
    content = re.sub(r'\{\s*year\s*\}', context.year, content)
    content = re.sub(r'\{\s*organization\s*\}', context.organization, content)
    content = re.sub(r'\{\s*project\s*\}', context.project, content)
    
    s = StringIO()
    s.write(content)
    s.seek(0)
    return s

def format_license(content_sio, lang):
    content_sio.seek(0)
    content = content_sio.read()
    
    if lang == 'py':
        lines = content.splitlines()
        formatted = "\n".join([f"# {line}" for line in lines])
    elif lang == 'js' or lang == 'ts':
        lines = content.splitlines()
        formatted = "\n".join([f" * {line}" for line in lines])
        formatted = "/*\n" + formatted + "\n */"
    elif lang == 'c' or lang == 'cpp':
        lines = content.splitlines()
        formatted = "\n".join([f" * {line}" for line in lines])
        formatted = "/*\n" + formatted + "\n */"
    else:
        # Default: just return as is
        formatted = content
        
    s = StringIO()
    s.write(formatted)
    s.seek(0)
    return s

def main():
    parser = argparse.ArgumentParser(description="Lice License Generator")
    parser.add_argument('license', nargs='?', help='The type of license to generate')
    parser.add_argument('-o', '--org', help='The organization under which the license is registered')
    parser.add_argument('-p', '--proj', help='The project name')
    parser.add_argument('-t', '--template', help='Path to a custom license template file')
    parser.add_argument('-y', '--year', help='The copyright year')
    parser.add_argument('-l', '--language', help='The language for the license header')
    parser.add_argument('-f', '--file', help='The output file name')
    parser.add_argument('--header', action='store_true', help='Generate a header instead of full license')
    parser.add_argument('--vars', action='store_true', help='List all template variables')

    args = parser.parse_args()

    try:
        if args.vars:
            if not args.license:
                print("Error: --vars requires a license type.")
                sys.exit(1)
            template = load_template(args.license, header=False)
            variables = extract_vars(template)
            print(", ".join(variables))
            return

        if not args.license and not args.template:
            # If no license specified, we might be in a mode where we just want to see help or something, 
            # but based on PRD, license is usually provided.
            parser.print_help()
            return

        # 1. Load Template
        if args.template:
            template_sio = load_file_template(args.template)
        else:
            template_sio = load_template(args.license, header=args.header)

        # 2. Get Context
        context = get_context(args)

        # 3. Generate License
        generated_sio = generate_license(template_sio, context)

        # 4. Format License
        if args.language:
            final_sio = format_license(generated_sio, args.language)
        else:
            final_sio = generated_sio

        output = final_sio.getvalue()

        # 5. Output
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
