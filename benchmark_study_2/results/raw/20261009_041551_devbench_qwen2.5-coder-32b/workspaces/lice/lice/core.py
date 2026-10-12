import argparse
import os
import sys
from io import StringIO

LICENSES = [
    "AGPL3",
    "Apache",
    "BSD2",
    "BSD3",
    # Add more licenses as needed
]

class Context:
    def __init__(self, year, organization, project):
        self.year = year
        self.organization = organization
        self.project = project

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

    if args.vars:
        # Implement listing of template variables
        print("Listing template variables for the specified license.")
        return

    context = get_context(args)

    if args.template:
        template_path = clean_path(args.template)
        template = load_file_template(template_path)
    else:
        template = load_template(args.license, args.language is not None)

    content = generate_license(template, context)

    if args.language:
        content = format_license(content, args.language)

    if args.file:
        suffix = get_suffix(args.file)
        if not suffix:
            args.file += get_suffix_from_language(args.language)
        with open(args.file, "w") as f:
            f.write(content.getvalue())
    else:
        print(content.getvalue())

def guess_organization():
    try:
        import subprocess
        return subprocess.check_output(['git', 'config', 'user.email']).strip().decode('utf-8').split('@')[0]
    except Exception:
        return os.getenv("USER", "Unknown Organization")

def load_file_template(path: str) -> StringIO:
    with open(path, "r") as f:
        return StringIO(f.read())

def load_template(license: str, header: bool = False) -> StringIO:
    # Implement loading of license template
    template_name = f"template-{license.lower()}-header.txt" if header else f"template-{license.lower()}.txt"
    template_path = os.path.join(os.path.dirname(__file__), "templates", template_name)
    with open(template_path, "r") as f:
        return StringIO(f.read())

def generate_license(template: StringIO, context: Context) -> StringIO:
    # Implement generation of license content
    template_content = template.getvalue()
    variables = extract_vars(template)
    for var in variables:
        if hasattr(context, var):
            template_content = template_content.replace(f"{{{var}}}", getattr(context, var))
    return StringIO(template_content)

def format_license(template: StringIO, lang: str) -> StringIO:
    # Implement formatting of license for specific language
    content = template.getvalue()
    comment_styles = {
        "py": ("# ", "#"),
        "js": ("// ", "//"),
        "java": ("// ", "//"),
        "c": ("/* ", " */"),
        "cpp": ("/* ", " */"),
        "h": ("/* ", " */"),
        "sh": ("# ", "#"),
        "rb": ("# ", "#"),
        "php": ("// ", "//"),
        "html": ("<!-- ", " -->"),
        "css": ("/* ", " */"),
        "go": ("// ", "//"),
        "swift": ("// ", "//"),
        "ts": ("// ", "//"),
        "tsx": ("// ", "//"),
        "jsx": ("// ", "//"),
        "vue": ("<!-- ", " -->"),
        "xml": ("<!-- ", " -->"),
        "json": ("", ""),  # JSON does not support comments
    }
    start, end = comment_styles.get(lang, ("", ""))
    formatted_content = "\n".join([f"{start}{line}{end}" for line in content.splitlines()])
    return StringIO(formatted_content)

def get_suffix(name: str) -> str | bool:
    suffix = os.path.splitext(name)[1]
    return suffix if suffix else False

def get_suffix_from_language(lang: str) -> str:
    language_suffixes = {
        "py": ".py",
        "js": ".js",
        "java": ".java",
        "c": ".c",
        "cpp": ".cpp",
        "h": ".h",
        "sh": ".sh",
        "rb": ".rb",
        "php": ".php",
        "html": ".html",
        "css": ".css",
        "go": ".go",
        "swift": ".swift",
        "ts": ".ts",
        "tsx": ".tsx",
        "jsx": ".jsx",
        "vue": ".vue",
        "xml": ".xml",
        "json": ".json",
    }
    return language_suffixes.get(lang, "")

def get_context(args):
    year = args.year or str(os.getenv("YEAR", "2023"))
    organization = args.org or guess_organization()
    project = args.proj or os.getenv("PROJECT", "Unknown Project")
    return Context(year, organization, project)

def extract_vars(template: StringIO) -> list:
    import re
    template_content = template.getvalue()
    return re.findall(r'\{(\w+)\}', template_content)

def clean_path(p: str) -> str:
    p = os.path.expanduser(p)
    p = os.path.abspath(p)
    if not os.path.exists(p):
        raise FileNotFoundError(f"The path {p} does not exist.")
    if not os.path.isfile(p):
        raise IsADirectoryError(f"The path {p} is not a file.")
    return p
