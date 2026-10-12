import argparse
import os
import sys
import datetime
from io import StringIO

LICENSES = [
    "AGPL3",
    "Apache",
    "BSD2",
    "BSD3",
    # Add more licenses as needed
]

def main():
    parser = argparse.ArgumentParser(description="Generate license files for software projects.")
    parser.add_argument("license", choices=LICENSES, help="The type of license to generate.")
    parser.add_argument("-o", "--org", help="The organization under which the license is registered.")
    parser.add_argument("-p", "--proj", help="The project name for which the license is generated.")
    parser.add_argument("-t", "--template", help="The path to a custom license template file.")
    parser.add_argument("-y", "--year", help="The copyright year to be listed in the license.")
    parser.add_argument("-l", "--language", help="The language for which the license header should be formatted.")
    parser.add_argument("-f", "--file", help="The output file name where the license should be saved.")
    parser.add_argument("--vars", action="store_true", help="List all template variables for the specified license.")

    args = parser.parse_args()

    context = get_context(args)
    template = load_template(args.license, args.header if 'header' in args else False, args)
    content = generate_license(template, context)

    if args.language:
        content = format_license(content, args.language)

    if args.file:
        with open(args.file, 'w') as f:
            f.write(content.getvalue())
    else:
        print(content.getvalue())

def clean_path(p):
    return os.path.abspath(os.path.expanduser(os.path.normpath(p)))

def get_context(args):
    year = args.year or str(datetime.datetime.now().year)
    organization = args.org or guess_organization()
    project = args.proj or os.path.basename(os.getcwd())
    return Context(year, organization, project)

def guess_organization():
    try:
        import subprocess
        # Try to get organization from git config
        try:
            return subprocess.check_output(['git', 'config', 'user.email']).strip().decode('utf-8').split('@')[0]
        except:
            pass
        # Try to get organization from git config (if set)
        try:
            return subprocess.check_output(['git', 'config', 'user.organization']).strip().decode('utf-8')
        except:
            pass
    except:
        pass
    # Fallback to USER environment variable
    return os.getenv('USER', 'Unknown')

def load_file_template(path):
    with open(clean_path(path), 'r') as f:
        return StringIO(f.read())

def load_template(license, header=False, args=None):
    if args and args.template:
        return load_file_template(args.template)
    template_name = f"template-{license.lower()}-header.txt" if header else f"template-{license.lower()}.txt"
    template_path = os.path.join(os.path.dirname(__file__), 'templates', template_name)
    return load_file_template(template_path)

def extract_vars(template):
    return [line.strip() for line in template.readlines() if line.startswith('##')]

def generate_license(template, context):
    content = template.getvalue()
    content = content.replace('##year##', context.year)
    content = content.replace('##organization##', context.organization)
    content = content.replace('##project##', context.project)
    return StringIO(content)

def format_license(template, lang):
    suffix = get_suffix(lang)
    if suffix:
        lines = template.getvalue().splitlines()
        if suffix == '/*':
            formatted_lines = [f"{suffix} {lines[0]}"] + [f" * {line}" for line in lines[1:-1]] + [f" {suffix}*/"]
        elif suffix == '<!--':
            formatted_lines = [f"{suffix} {lines[0]}"] + [f" {line}" for line in lines[1:-1]] + [f"{suffix}-->"]
        else:
            formatted_lines = [f"{suffix} {line}" for line in lines]
        return StringIO('\n'.join(formatted_lines))
    return template

def get_suffix(name):
    language_suffixes = {
        'py': '#',
        'js': '//',
        'java': '//',
        'c': '//',
        'cpp': '//',
        'h': '//',
        'sh': '#',
        'rb': '#',
        'php': '//',
        'html': '<!--',
        'css': '/*',
        # Add more languages and their comment suffixes as needed
    }
    return language_suffixes.get(name)

class Context:
    def __init__(self, year, organization, project):
        self.year = year
        self.organization = organization
        self.project = project

if __name__ == "__main__":
    main()
