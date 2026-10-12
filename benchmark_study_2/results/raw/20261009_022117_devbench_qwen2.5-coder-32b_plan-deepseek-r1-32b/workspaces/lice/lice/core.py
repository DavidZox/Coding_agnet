import os
import argparse
import subprocess
from io import StringIO
import re

class Context:
    def __init__(self, year, organization, project):
        self.year = year
        self.organization = organization
        self.project = project

def clean_path(p):
    return os.path.abspath(os.path.normpath(p))

def get_context(args):
    parser = argparse.ArgumentParser(description='Generate license files for software projects.')
    parser.add_argument('license', type=str, help='The type of license to generate.')
    parser.add_argument('-o', '--org', type=str, help='The organization under which the license is registered.')
    parser.add_argument('-p', '--proj', type=str, help='The project name for which the license is generated.')
    parser.add_argument('-y', '--year', type=str, help='The copyright year to be listed in the license.')
    parsed_args = parser.parse_args(args)

    year = parsed_args.year or str(os.getenv('YEAR', '2023'))  # Default to current year if not provided
    organization = parsed_args.org or guess_organization()  # Default to guessed organization if not provided
    project = parsed_args.proj or os.getenv('PROJECT', 'Unknown Project')  # Default to 'Unknown Project' if not provided

    return Context(year, organization, project)

def guess_organization():
    try:
        # Try to get organization from git config
        org = subprocess.check_output(['git', 'config', 'user.name']).strip().decode('utf-8')
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fallback to environment variable if git config fails
        org = os.getenv('ORG', 'Unknown Organization')
    return org

def load_file_template(path):
    with open(path, 'r') as file:
        content = file.read()
    template = StringIO()
    template.write(content)
    template.seek(0)
    return template

def load_template(license: str, header: bool = False):
    template_name = f"template-{license.lower()}-header.txt" if header else f"template-{license.lower()}.txt"
    template_path = os.path.join(os.path.dirname(__file__), 'templates', template_name)
    return load_file_template(template_path)

def extract_vars(template: StringIO) -> list:
    template.seek(0)
    content = template.read()
    # Use regex to find all occurrences of {{ variable }}
    variables = re.findall(r'{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}', content)
    return list(set(variables))

def generate_license(template: StringIO, context: Context) -> StringIO:
    template.seek(0)
    content = template.read()
    for var in extract_vars(template):
        value = getattr(context, var, f"{{{var}}}")
        content = content.replace(f"{{{{ {var} }}}}", value)
    formatted_license = StringIO()
    formatted_license.write(content)
    formatted_license.seek(0)
    return formatted_license

def format_license(template: StringIO, lang: str) -> StringIO:
    template.seek(0)
    content = template.read()
    comment_styles = {
        'py': ('# ', '#'),
        'js': ('// ', '//'),
        'java': ('// ', '//'),
        'c': ('/* ', ' */'),
        'cpp': ('/* ', ' */'),
        'h': ('/* ', ' */'),
        'sh': ('# ', '#'),
        'rb': ('# ', '#'),
        'php': ('// ', '//'),
        'html': ('<!-- ', ' -->'),
        'css': ('/* ', ' */'),
        'go': ('// ', '//'),
        'swift': ('// ', '//'),
        'ts': ('// ', '//'),
        'tsx': ('// ', '//'),
        'vue': ('<!-- ', ' -->'),
        'xml': ('<!-- ', ' -->'),
        'json': ('', ''),  # JSON does not support comments
        'md': ('<!-- ', ' -->'),
        'rst': ('.. ', '..'),  # reStructuredText uses '..' for comments
    }
    start_comment, end_comment = comment_styles.get(lang, ('', ''))
    if start_comment and end_comment:
        formatted_content = '\n'.join(f"{start_comment}{line}{end_comment}" for line in content.splitlines())
    else:
        formatted_content = content
    formatted_license = StringIO()
    formatted_license.write(formatted_content)
    formatted_license.seek(0)
    return formatted_license

def main():
    import sys
    args = sys.argv[1:]
    context = get_context(args)
    license_type = context.license
    header = '--header' in args
    language = next((arg.split('=')[1] for arg in args if arg.startswith('--language=')), None)
    output_file = next((arg.split('=')[1] for arg in args if arg.startswith('--file=')), None)

    template = load_template(license_type, header)
    license_content = generate_license(template, context)

    if language:
        license_content = format_license(license_content, language)

    if output_file:
        with open(output_file, 'w') as file:
            file.write(license_content.getvalue())
    else:
        print(license_content.getvalue())

if __name__ == "__main__":
    main()
