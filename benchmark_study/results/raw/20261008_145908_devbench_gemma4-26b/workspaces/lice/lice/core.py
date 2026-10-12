import argparse
import os
import sys
import subprocess
import re
from io import StringIO
from typing import List, Union, Optional

# Constants for templates (In a real scenario, these would be loaded from files)
# For this implementation, we assume the existence of a 'templates' directory.
TEMPLATES_DIR = "templates"

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
    return os.path.normpath(p)

def guess_organization() -> str:
    # Try git config
    try:
        org = subprocess.check_output(["git", "config", "user.name"], stderr=subprocess.DEVNULL).decode().strip()
        if org:
            return org
    except Exception:
        pass
    
    # Try environment variable
    return os.environ.get("USER", "Unknown")

def load_file_template(path: str) -> StringIO:
    with open(path, 'r') as f:
        return StringIO(f.read())

def load_template(license_type: str, header: bool = False) -> StringIO:
    suffix = "-header" if header else ""
    # Mapping license names to template filenames (simplified)
    # In actual implementation, this would match the templates folder files
    filename = f"template-{license_type.lower()}{suffix}.txt"
    path = os.path.join(TEMPLATES_DIR, filename)
    
    if not os.path.exists(path):
        # Fallback for demonstration if templates don't exist in the environment
        return StringIO(f"Template for {license_type} {'(header)' if header else ''}")
    
    return load_file_template(path)

def extract_vars(template: StringIO) -> List[str]:
    template.seek(0)
    content = template.read()
    return re.findall(r"\{\{\s*(\w+)\s*\}\}", content)

def generate_license(template: StringIO, context: Context) -> StringIO:
    template.seek(0)
    content = template.read()
    
    # Replace {{ var }} or {{var}} or {{ var }}
    def replace_match(match):
        var_name = match.group(1).strip()
        if var_name == "year":
            return context.year
        elif var_name == "organization":
            return context.organization
        elif var_name == "project":
            return context.project
        return match.group(0)

    content = re.sub(r"\{\{\s*(\w+)\s*\}\}", replace_match, content)
    return StringIO(content)

def format_license(content_io: StringIO, lang: str) -> StringIO:
    content_io.seek(0)
    lines = content_io.readlines()
    
    if lang == "py":
        formatted = ["# " + line.rstrip() for line in lines]
    elif lang == "js" or lang == "ts":
        formatted = ["/* " + line.rstrip() + " */" for line in lines]
    else:
        formatted = lines
        
    return StringIO("\n".join(formatted) + ("\n" if formatted and not formatted[-1].endswith('\n') else ""))

def get_suffix(name: str) -> Union[str, bool]:
    if "." in name:
        return name.split(".")[-1]
    return False

def get_context(args: argparse.Namespace) -> Context:
    year = args.year if args.year else "2023" # Default year
    org = args.org if args.org else guess_organization()
    proj = args.proj if args.proj else ""
    return Context(year, org, proj)

def main():
    parser = argparse.ArgumentParser(description="Lice License Generator")
    parser.add_argument("license", nargs="?", help="The type of license to generate")
    parser.add_argument("-o", "--org", help="The organization")
    parser.add_argument("-p", "--proj", help="The project name")
    parser.add_argument("-t", "--template", help="Path to a custom template")
    parser.add_argument("-y", "--year", help="The copyright year")
    parser.add_argument("-l", "--language", help="The language for header formatting")
    parser.add_argument("-f", "--file", help="Output file name")
    parser.add_argument("--vars", action="store_true", help="List template variables")

    args = parser.parse_args()

    if not args.license and not args.language and not args.template:
        parser.print_help()
        return

    if args.vars and args.license:
        template = load_template(args.license)
        print(extract_vars(template))
        return

    if args.template:
        template_io = load_file_template(args.template)
    elif args.license:
        is_header = args.language is not None
        template_io = load_template(args.license, header=is_header)
    else:
        return

    context = get_context(args)
    
    # If it's a header, we might need to handle it differently, 
    # but the UML suggests generate_license takes the template.
    generated_io = generate_license(template_io, context)

    if args.language:
        final_io = format_license(generated_io, args.language)
    else:
        final_io = generated_io

    output = final_io.getvalue()

    if args.file:
        with open(args.file, 'w') as f:
            f.write(output)
    else:
        print(output)

if __name__ == "__main__":
    main()
