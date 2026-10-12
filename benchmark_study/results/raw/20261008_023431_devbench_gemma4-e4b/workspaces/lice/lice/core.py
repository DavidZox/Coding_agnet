import argparse
import os
import sys
from typing import List, Optional
from io import StringIO
import subprocess # Added for git config

# --- Mock/Placeholder Classes based on UML_class.md ---
# Since we are only implementing core.py, we mock dependencies that are not fully defined yet.

class Context:
    """Holds context information for license generation."""
    def __init__(self, year: Optional[str], organization: Optional[str], project: Optional[str]):
        self.year = year
        self.organization = organization
        self.project = project

class ArgumentParser:
    """Mock for argument parsing structure, mimicking argparse behavior for testing."""
    def __init__(self):
        self.args = {}
        self._arguments = [] # Changed from dict to list

    def add_argument(self, *args, **kwargs):
        # Mock implementation to store argument definitions
        self._arguments.append({'args': args, 'kwargs': kwargs})

    def parse_args(self, args_list: List[str] = None):
        # Simple mock parser to populate self.args based on provided list
        if args_list is None:
            args_list = []
            
        self.args = {}
        i = 0
        while i < len(args_list):
            arg = args_list[i]
            if arg.startswith('-'):
                # Handle flags or options
                if arg in ('--header', '-h'):
                    self.args['header'] = True
                    i += 1
                elif arg in ('--vars', '-v'):
                    self.args['vars'] = True
                    i += 1
                elif arg.startswith('-o') or arg.startswith('--org'):
                    self.args['org'] = args_list[i+1]
                    i += 2
                elif arg.startswith('-p') or arg.startswith('--proj'):
                    self.args['proj'] = args_list[i+1]
                    i += 2
                elif arg.startswith('-y') or arg.startswith('--year'):
                    self.args['year'] = args_list[i+1]
                    i += 2
                elif arg.startswith('-l') or arg.startswith('--language'):
                    self.args['language'] = args_list[i+1]
                    i += 2
                elif arg.startswith('-f') or arg.startswith('--file'):
                    self.args['file'] = args_list[i+1]
                    i += 2
                else:
                    i += 1 # Skip unknown flags
            elif arg not in ('mit', 'bsd3', 'gpl3', 'apache') and not arg.startswith('-'):
                # Handle positional argument (license type)
                self.args['license'] = arg
                i += 1
            else:
                i += 1
        return self.args

class StringIO:
    """Mock for in-memory file stream."""
    def __init__(self):
        self._buffer = []

    def write(self, s: str):
        self._buffer.append(s)

    def getvalue(self) -> str:
        return "".join(self._buffer)

    def close(self):
        pass

    def seek(self, index: int):
        pass

    def readlines(self) -> List[str]:
        return "".join(self._buffer).splitlines()

# --- Global Functions Implementation ---

class GlobalFunctions:
    """
    Hosts the main logic functions as per UML_class.md.
    """
    def __init__(self):
        pass

    def guess_organization(self) -> str:
        """
        Attempts to determine the user's organization from git config or the USER environment variable.
        """
        # 1. Check environment variable $USER (or a custom one like USER_ORG if needed, sticking to PRD requirement)
        # The PRD mentions $USER, but often organization is stored elsewhere. We check USER first, then git.
        user_name = os.environ.get("USER")
        if user_name:
            # Simple heuristic: if USER is set, we might use it as a fallback, 
            # but for organization, we prioritize git config or a specific env var if available.
            pass 

        # 2. Check git config for user.organization
        try:
            result = subprocess.run(
                ['git', 'config', 'user.organization'], 
                capture_output=True, 
                text=True, 
                check=False
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except FileNotFoundError:
            # git command not found
            pass
        except Exception:
            # Other git execution errors
            pass

        # 3. Fallback to environment variable (if a specific organization env var was intended, e.g., USER_ORG)
        org = os.environ.get("USER_ORG")
        if org:
            return org
        
        # Default fallback
        return "DefaultOrg"

    def load_file_template(self, path: str) -> StringIO:
        """
        Loads content from a specified file path into a StringIO object.
        """
        try:
            with open(path, 'r') as f:
                content = f.read()
            sio = StringIO()
            sio.write(content)
            return sio
        except FileNotFoundError:
            print(f"Error: Template file not found at {path}", file=sys.stderr)
            sys.exit(1)

    def load_template(self, license: str, header: bool = False) -> StringIO:
        """
        Loads the appropriate license template (full or header) from the templates directory.
        """
        templates_dir = "templates"
        
        if header:
            template_name = f"template-{license}-header.txt"
        else:
            template_name = f"template-{license}.txt"
        
        path = os.path.join(templates_dir, template_name)
        return self.load_file_template(path)

    def extract_vars(self, template: StringIO) -> List[str]:
        """
        Extracts all template variables (placeholders) from the template content.
        (Mock implementation: assumes variables are in {{...}} format)
        """
        content = template.getvalue()
        import re
        # Simple regex to find placeholders like {{YEAR}} or {{ORG}}
        vars_list = re.findall(r"\{\{(\w+)\}\}", content)
        return list(set(vars_list))

    def generate_license(self, template: StringIO, context: Context) -> StringIO:
        """
        Generates the license text by substituting placeholders in the template with context data.
        """
        content = template.getvalue()
        
        # Substitution logic based on Context object
        replacements = {
            "{{YEAR}}": context.year if context.year else "YYYY",
            "{{ORG}}": context.organization if context.organization else "OrganizationName",
            "{{PROJECT}}": context.project if context.project else "ProjectName",
        }
        
        generated_content = content
        for placeholder, value in replacements.items():
            generated_content = generated_content.replace(placeholder, value)
            
        sio = StringIO()
        sio.write(generated_content)
        return sio

    def format_license(self, template: StringIO, lang: str) -> StringIO:
        """
        Formats the license text according to the specified programming language comment style.
        (Mock implementation: prepends language-specific header/comments)
        """
        content = template.getvalue()
        
        # Mock formatting logic
        # Note: In a real scenario, we'd need the actual license type from the template content 
        # to correctly populate the header, but we follow the existing mock structure.
        
        # Attempt to extract license type from the first line of the template content
        license_type_placeholder = "LICENSE_TYPE"
        if content:
            first_line = content.splitlines()[0]
            # Crude attempt to get license name if it's in the first line
            if "template-" in first_line:
                license_type_placeholder = first_line.split("-")[-1].upper()
            elif "LICENSE" in first_line:
                 license_type_placeholder = "LICENSE"


        if lang == 'py':
            formatted = f'# -*- coding: utf-8 -*-\n# Copyright {{YEAR}} {{ORG}} for {{PROJECT}}\n# Licensed under {license_type_placeholder}\n\n{content}'
        elif lang == 'c':
            formatted = f"/*\n * Copyright {{YEAR}} {{ORG}} for {{PROJECT}}\n * Licensed under {license_type_placeholder}\n */\n\n{content}"
        else:
            formatted = f"--- License for {lang.upper()} ---\n{content}"
            
        sio = StringIO()
        sio.write(formatted)
        return sio

    def get_suffix(self, name: str) -> str | bool:
        """
        Determines the appropriate suffix for a given name (e.g., for file extensions).
        """
        # Mock implementation
        if name.endswith(".py"):
            return "py"
        return "unknown"

    def get_suffix(self, name: str) -> str | bool:
        """
        Determines the appropriate suffix for a given name (e.g., for file extensions).
        """
        # Mock implementation
        if name.endswith(".py"):
            return "py"
        return "unknown"

def guess_organization() -> str:
    """
    Attempts to determine the user's organization from git config or the USER environment variable.
    """
    # 1. Check git config for user.organization
    try:
        result = subprocess.run(
            ['git', 'config', 'user.organization'], 
            capture_output=True, 
            text=True, 
            check=False
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except FileNotFoundError:
        # git command not found
        pass
    except Exception:
        # Other git execution errors
        pass

    # 2. Fallback to environment variable $USER
    user_name = os.environ.get("USER")
    if user_name:
        # Simple heuristic: if USER is set, we might use it as a fallback, 
        # but for organization, we prioritize git config or a specific env var if available.
        pass 

    # 3. Fallback to environment variable USER_ORG (as a specific organizational env var)
    org = os.environ.get("USER_ORG")
    if org:
        return org
    
    # Default fallback
    return "DefaultOrg"

def get_context(args: argparse.Namespace) -> Context:
    """
    Constructs and returns a Context object from parsed arguments.
    """
    # Determine Organization: Use provided args.org, otherwise call guess_organization()
    org_to_use = args.org if args.org else guess_organization()
    
    return Context(
        year=args.year,
        organization=org_to_use,
        project=args.proj
    )

# Instantiate the global functions class for use in core.py
global_functions = GlobalFunctions()

# --- Main CLI Logic ---

def main(args: argparse.Namespace):
    """
    Main entry point for the lice CLI.
    Parses command-line arguments and delegates to core logic.
    """
    
    # 1. Determine Context
    # Use args.org if provided, otherwise call guess_organization()
    org_to_use = args.org if args.org else guess_organization()
    
    context = Context(
        year=args.year,
        organization=org_to_use,
        project=args.proj
    )
    
    # 2. Handle --vars option
    if args.vars:
        if not args.license:
            print("Error: --vars requires a license type to be specified.", file=sys.stderr)
            sys.exit(1)
        
        # Load template just to extract variables
        try:
            template_sio = load_template(args.license, header=False)
            vars_list = extract_vars(template_sio)
            print(f"Template variables for {args.license}: {', '.join(vars_list)}")
        except SystemExit:
            # Catch exit from load_template if file not found
            pass
        return

    # 3. Handle License Generation
    if not args.license:
        print("Error: License type must be specified.", file=sys.stderr)
        sys.exit(1)

    try:
        # 3a. Load Template
        is_header = args.header
        template_sio = load_template(args.license, is_header)

        # 3b. Generate License Content
        generated_sio = generate_license(template_sio, context)
        
        final_content_sio = generated_sio
        
        # 3c. Format License (if language is specified)
        if args.language:
            # Pass the generated content (which contains placeholders) to format_license
            # Note: format_license expects a StringIO object, so we pass generated_sio
            final_content_sio = format_license(generated_sio, args.language)
        
        final_content = final_content_sio.getvalue()

        # 4. Output Result
        if args.file:
            # Save to file
            with open(args.file, 'w') as f:
                f.write(final_content)
            print(f"Successfully generated {args.license} license saved to {args.file}")
        else:
            # Print to stdout
            print(final_content)

    except SystemExit:
        # Propagate exit from load_template if necessary
        pass
    except Exception as e:
        print(f"An unexpected error occurred during license generation: {e}", file=sys.stderr)
        sys.exit(1)

def guess_organization() -> str:
    """
    Attempts to determine the user's organization from git config or the USER environment variable.
    """
    # 1. Check git config for user.organization
    try:
        result = subprocess.run(
            ['git', 'config', 'user.organization'], 
            capture_output=True, 
            text=True, 
            check=False
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except FileNotFoundError:
        # git command not found
        pass
    except Exception:
        # Other git execution errors
        pass

    # 2. Fallback to environment variable $USER
    user_name = os.environ.get("USER")
    if user_name:
        # Simple heuristic: if USER is set, we might use it as a fallback, 
        # but for organization, we prioritize git config or a specific env var if available.
        pass 

    # 3. Fallback to environment variable USER_ORG (as a specific organizational env var)
    org = os.environ.get("USER_ORG")
    if org:
        return org
    
    # Default fallback
    return "DefaultOrg"

def get_context(args: argparse.Namespace) -> Context:
    """
    Constructs and returns a Context object from parsed arguments.
    """
    # Determine Organization: Use provided args.org, otherwise call guess_organization()
    org_to_use = args.org if args.org else guess_organization()
    
    return Context(
        year=args.year,
        organization=org_to_use,
        project=args.proj
    )

# Instantiate the global functions class for use in core.py
global_functions = GlobalFunctions()

# --- Main CLI Logic ---

def main(args: argparse.Namespace):
    """
    Main entry point for the lice CLI.
    Parses command-line arguments and delegates to core logic.
    """
    
    # 1. Determine Context
    # Use args.org if provided, otherwise call guess_organization()
    org_to_use = args.org if args.org else guess_organization()
    
    context = Context(
        year=args.year,
        organization=org_to_use,
        project=args.proj
    )
    
    # 2. Handle --vars option
    if args.vars:
        if not args.license:
            print("Error: --vars requires a license type to be specified.", file=sys.stderr)
            sys.exit(1)
        
        # Load template just to extract variables
        try:
            template_sio = load_template(args.license, header=False)
            vars_list = extract_vars(template_sio)
            print(f"Template variables for {args.license}: {', '.join(vars_list)}")
        except SystemExit:
            # Catch exit from load_template if file not found
            pass
        return

    # 3. Handle License Generation
    if not args.license:
        print("Error: License type must be specified.", file=sys.stderr)
        sys.exit(1)

    try:
        # 3a. Load Template
        is_header = args.header
        template_sio = load_template(args.license, is_header)

        # 3b. Generate License Content
        generated_sio = generate_license(template_sio, context)
        
        final_content_sio = generated_sio
        
        # 3c. Format License (if language is specified)
        if args.language:
            # Pass the generated content (which contains placeholders) to format_license
            # Note: format_license expects a StringIO object, so we pass generated_sio
            final_content_sio = format_license(generated_sio, args.language)
        
        final_content = final_content_sio.getvalue()

        # 4. Output Result
        if args.file:
            # Save to file
            with open(args.file, 'w') as f:
                f.write(final_content)
            print(f"Successfully generated {args.license} license saved to {args.file}")
        else:
            # Print to stdout
            print(final_content)

    except SystemExit:
        # Propagate exit from load_template if necessary
        pass
    except Exception as e:
        print(f"An unexpected error occurred during license generation: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    # This block is for direct execution testing, but the CLI entry point is handled by __init__.py
    # We keep it minimal as the primary entry point is expected to be via 'python -m lice'
    pass
