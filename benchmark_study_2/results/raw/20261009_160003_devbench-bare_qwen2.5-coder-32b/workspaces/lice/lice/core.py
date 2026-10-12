import os
import sys
import argparse
import io
from enum import Enum

class LICENSES(Enum):
    AGPL3 = "agpl3"
    Apache = "apache"
    BSD2 = "bsd2"
    BSD3 = "bsd3"
    # Add more licenses as needed

class Context:
    def __init__(self, year, organization, project):
        self.year = year
        self.organization = organization
        self.project = project

def main():
    parser = argparse.ArgumentParser(description="Generate license files for software projects.")
    parser.add_argument('license', type=str, help='The type of license to generate.')
    parser.add_argument('-o', '--org', type=str, help='The organization under which the license is registered.')
    parser.add_argument('-p', '--proj', type=str, help='The project name for which the license is generated.')
    parser.add_argument('-t', '--template', type=str, help='The path to a custom license template file.')
    parser.add_argument('-y', '--year', type=str, help='The copyright year to be listed in the license.')
    parser.add_argument('-l', '--language', type=str, help='The language for which the license header should be formatted.')
    parser.add_argument('-f', '--file', type=str, help='The output file name where the license should be saved.')
    parser.add_argument('--vars', action='store_true', help='List all template variables for the specified license.')

    args = parser.parse_args()
    context = get_context(args)
    template = load_template(args.license, args.header)
    content = generate_license(template, context)
    formatted_license = format_license(content, args.language)

    if args.file:
        with open(args.file, 'w') as f:
            f.write(formatted_license.getvalue())
    else:
        print(formatted_license.getvalue())

def clean_path(p):
    return os.path.abspath(os.path.expanduser(p))

def get_context(args):
    year = args.year or str(datetime.datetime.now().year)
    organization = args.org or guess_organization()
    project = args.proj or os.path.basename(os.getcwd())
    return Context(year, organization, project)

def guess_organization():
    try:
        import git
        repo = git.Repo(os.getcwd(), search_parent_directories=True)
        config = repo.config_reader()
        return config.get_value('user', 'name')
    except (ModuleNotFoundError, git.InvalidGitRepositoryError):
        return os.getenv('USER', 'Unknown Organization')

def load_file_template(path):
    with open(clean_path(path), 'r') as f:
        return io.StringIO(f.read())

def load_template(license, header):
    template_name = f"template-{license}-header.txt" if header else f"template-{license}.txt"
    template_path = os.path.join(os.path.dirname(__file__), 'templates', template_name)
    return load_file_template(template_path)

def extract_vars(template):
    return [line.strip() for line in template.readlines() if line.startswith('##')]

def generate_license(template, context):
    content = template.getvalue()
    content = content.replace('##year##', context.year)
    content = content.replace('##organization##', context.organization)
    content = content.replace('##project##', context.project)
    return io.StringIO(content)

def format_license(template, lang):
    suffix = get_suffix(lang)
    if suffix:
        lines = template.readlines()
        formatted_lines = [f"{suffix} {line}" for line in lines]
        return io.StringIO(''.join(formatted_lines))
    return template

def get_suffix(name):
    language_suffixes = {
        'py': '#',
        'js': '//',
        'java': '//',
        'cpp': '//',
        'c': '//',
        'sh': '#',
        'rb': '#',
        'php': '//',
        'html': '<!--',
        'css': '/*',
        'swift': '//',
        'go': '//',
        'ts': '//',
        'scala': '//',
        'rust': '//',
        'kotlin': '//',
        'dart': '//',
        'perl': '#',
        'r': '#',
        'sql': '--',
        'pl': '#',
        'vue': '<!--',
        'tsx': '//',
        'jsx': '//',
        'svelte': '<!--',
        'h': '//',
        'hpp': '//',
        'cs': '//',
        'm': '//',
        'mm': '//',
        'swift': '//',
        'groovy': '//',
        'scala': '//',
        'rs': '//',
        'kt': '//',
        'dart': '//',
        'perl': '#',
        'r': '#',
        'sql': '--',
        'pl': '#',
        'vue': '<!--',
        'tsx': '//',
        'jsx': '//',
        'svelte': '<!--',
        'h': '//',
        'hpp': '//',
        'cs': '//',
        'm': '//',
        'mm': '//',
    }
    return language_suffixes.get(name)

if __name__ == "__main__":
    main()
