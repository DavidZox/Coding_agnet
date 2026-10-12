import os
import sys
import argparse
from io import StringIO
from enum import Enum
import datetime

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
    parser.add_argument("license", type=str, help="The type of license to generate.")
    parser.add_argument("-o", "--org", type=str, help="The organization under which the license is registered.")
    parser.add_argument("-p", "--proj", type=str, help="The project name for which the license is generated.")
    parser.add_argument("-t", "--template", type=str, help="The path to a custom license template file.")
    parser.add_argument("-y", "--year", type=str, help="The copyright year to be listed in the license.")
    parser.add_argument("-l", "--language", type=str, help="The language for which the license header should be formatted.")
    parser.add_argument("-f", "--file", type=str, help="The output file name where the license should be saved.")
    parser.add_argument("--vars", action="store_true", help="Option to list all template variables for the specified license.")
    parser.add_argument("--header", action="store_true", help="Generate a license header for a source file.")
    
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
        repo = git.Repo(search_parent_directories=True)
        config = repo.config_reader()
        return config.get_value('user', 'name')
    except (ImportError, ModuleNotFoundError):
        return os.getenv('USER', 'Unknown Organization')
    except git.InvalidGitRepositoryError:
        return os.getenv('USER', 'Unknown Organization')

def load_file_template(path):
    with open(clean_path(path), 'r') as f:
        return StringIO(f.read())

def load_template(license, header=False):
    template_name = f"template-{license}-header.txt" if header else f"template-{license}.txt"
    template_path = os.path.join(os.path.dirname(__file__), 'templates', template_name)
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template file not found: {template_path}")
    return load_file_template(template_path)

def extract_vars(template):
    variables = []
    for line in template.readlines():
        stripped_line = line.strip()
        if stripped_line.startswith("{{") and stripped_line.endswith("}}"):
            variables.append(stripped_line[2:-2])
    return variables

def generate_license(template, context):
    content = template.getvalue()
    variables = extract_vars(template)
    for var in variables:
        value = getattr(context, var, f"{{{var}}}")
        content = content.replace(f"{{{var}}}", value)
    return StringIO(content)

def format_license(template, lang):
    if not lang:
        return template
    
    suffix = get_suffix(lang)
    if not suffix:
        return template
    
    formatted_content = ""
    for line in template.readlines():
        if line.strip():  # Check if the line is not empty
            formatted_content += f"{suffix} {line}"
        else:
            formatted_content += f"{suffix}\n"  # Add a comment line for empty lines
    return StringIO(formatted_content)

def get_suffix(name):
    language_suffixes = {
        "py": "#",
        "js": "//",
        "java": "//",
        "c": "//",
        "cpp": "//",
        "h": "//",
        "sh": "#",
        "rb": "#",
        "php": "//",
        "html": "<!--",
        "css": "/*",
        "scss": "/*",
        "less": "/*",
        "md": "<!--",
        "rst": "..",
        "txt": "#"
    }
    return language_suffixes.get(name, False)
