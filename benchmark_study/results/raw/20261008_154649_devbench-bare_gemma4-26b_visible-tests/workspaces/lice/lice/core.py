import argparse
import os
import re
import subprocess
from io import StringIO
from pathlib import Path

# Enumeration of supported licenses as implied by tests and PRD
LICENSES = [
    "afl3", "agpl3", "apache", "bsd2", "bsd3", "cc_by", "mit", "gpl3"
]

class Context:
    def __init__(self, year, organization, project):
        self.year = year
        self.organization = organization
        self.project = project

def clean_path(p):
    """Transforms relative paths to absolute and expands environment variables."""
    if p == "~":
        return os.path.expanduser("~")
    # Handle $VAR or ${VAR}
    expanded = os.path.expandvars(p)
    return os.path.abspath(expanded)

def guess_organization():
    """Attempts to determine organization from git config or USER env."""
    try:
        # Try git config user.name as a fallback for organization
        org = subprocess.check_output(["git", "config", "user.name"], stderr=subprocess.DEVNULL).decode().strip()
        if org:
            return org
    except Exception:
        pass
    return os.environ.get("USER", "Unknown")

def get_context(args):
    """Creates a Context object from parsed arguments."""
    year = args.year if args.year else "2024" # Default fallback
    org = args.org if args.org else guess_organization()
    proj = args.proj if args.proj else ""
    return Context(year, org, proj)

def load_file_template(path):
    """Loads a template from a specific file path."""
    if not os.path.exists(path):
        raise ValueError(f"path does not exist: {path}")
    with open(path, 'r') as f:
        content = f.read()
    s = StringIO()
    s.write(content)
    s.seek(0)
    return s

def load_template(license_name, header=False):
    """Loads a template from the package templates directory."""
    suffix = "-header" if header else ""
    # In a real package, this would use pkg_resources or importlib.resources
    # For this implementation, we assume templates/ directory exists relative to execution
    path = f"templates/template-{license_name}{suffix}.txt"
    
    if not os.path.exists(path):
        raise IOError(f"Template {path} not found")
        
    with open(path, 'r') as f:
        content = f.read()
    s = StringIO()
    s.write(content)
    s.seek(0)
    return s

def extract_vars(template_io):
    """Extracts {{ variable }} placeholders from a template."""
    content = template_io.getvalue()
    return sorted(list(set(re.findall(r"\{\{\s*(\w+)\s*\}\}", content))))

def generate_license(template_io, context):
    """Replaces placeholders in template with context values."""
    content = template_io.getvalue()
    content = content.replace("{{ year }}", context.year)
    content = content.replace("{{ organization }}", context.organization)
    content = content.replace("{{ project }}", context.project)
    
    s = StringIO()
    s.write(content)
    s.seek(0)
    return s

def format_license(template_io, lang):
    """Formats the license text based on the programming language."""
    content = template_io.getvalue().strip()
    s = StringIO()
    if lang == "py":
        s.write(f"\n# {content}\n")
    elif lang in ["c", "cpp", "java"]:
        s.write(f"/*\n * {content} */\n")
    else:
        s.write(content)
    s.seek(0)
    return s

def get_suffix(name):
    """Returns the file extension if it's a recognized source file."""
    ext = os.path.splitext(name)[1][1:]
    if ext in ["py", "c", "cpp", "h", "java"]:
        return ext
    return False

def valid_year(value):
    """Validates that the year is a 4-digit string."""
    if not re.fullmatch(r"\d{4}", value):
        raise argparse.ArgumentTypeError(f"Invalid year: {value}")
    return value

def main():
    parser = argparse.ArgumentParser(description="Lice License Generator")
    parser.add_argument("license", nargs="?", default="bsd3", help="Type of license")
    parser.add_argument("-o", "--org", help="Organization name")
    parser.add_argument("-p", "--proj", help="Project name")
    parser.add_argument("-t", "--template", help="Custom template path")
    parser.add_argument("-y", "--year", type=valid_year, help="Copyright year")
    parser.add_argument("-l", "--language", help="Language for header formatting")
    parser.add_argument("-f", "--file", help="Output file name")
    parser.add_argument("--vars", action="store_true", help="List template variables")
    parser.add_argument("--languages", action="store_true", help="List supported languages")

    args = parser.parse_args()

    # Handle --languages
    if args.languages:
        print("cpp\npython\nc\njava")
        return

    # Handle --vars
    if args.vars:
        try:
            if args.template:
                template = load_file_template(args.template)
            else:
                template = load_template(args.license)
            vars_list = extract_vars(template)
            print(f"The {args.license} license template contains the following variables: {', '.join(vars_list)}")
        except Exception:
            pass
        return

    # Core Logic
    try:
        if args.template:
            template = load_file_template(args.template)
        else:
            # If license is provided as positional, it's the license type
            template = load_template(args.license)

        context = get_context(args)
        
        # If header is requested
        if args.language:
            template = load_template(args.license, header=True)
            
        generated_io = generate_license(template, context)
        
        if args.language:
            final_io = format_license(generated_io, args.language)
        else:
            final_io = generated_io

        output = final_io.getvalue()

        if args.file:
            with open(args.file, 'w') as f:
                f.write(output)
        else:
            print(output, end="")

    except Exception as e:
        if isinstance(e, ValueError) and "path does not exist" in str(e):
            raise e
        # For other errors, we might want to exit or print
        # But based on tests, we need to handle specific exits
        import sys
        sys.exit(1)

if __name__ == "__main__":
    main()
