"""
Lice License Generator Package.

A tool to streamline the creation of license files for software projects.
"""
__version__ = "0.1.0"

from .core import main

def run_lice(args_list: list[str] = None):
    """
    Entry point function to run the lice CLI tool.
    """
    main(args_list)
