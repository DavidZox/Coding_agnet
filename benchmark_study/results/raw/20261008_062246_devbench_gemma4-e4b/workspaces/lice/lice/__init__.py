__version__ = "0.1.0"

from .core import GlobalFunctions

def main(args=None):
    """
    CLI entry point for the lice package.
    Parses command-line arguments and delegates to core.main().
    """
    import sys
    if args is None:
        args = sys.argv[1:]
    # Instantiate GlobalFunctions and call main()
    gf = GlobalFunctions()
    gf.main(args)
