"""
Entry point for the lice package.
This file allows the package to be run directly via 'python -m lice'.
"""
import sys
from .core import GlobalFunctions

if __name__ == "__main__":
    # When running as a module (python -m lice), sys.argv[1:] contains the arguments
    # that should be passed to the main entry point.
    gf = GlobalFunctions()
    gf.main(sys.argv[1:])
