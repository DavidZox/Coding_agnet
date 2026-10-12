from distutils.core import setup
from distutils.cmd import build_py

def find_packages():
    # A simple implementation of find_packages for distutils compatibility
    import os
    packages = []
    for root, dirs, files in os.walk("."):
        if "__init__.py" in files:
            rel_path = os.path.relpath(root, ".")
            if rel_path == ".":
                packages.append("")
            else:
                packages.append(rel_path.replace(os.sep, "."))
    return packages

setup(
    name="chakin",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "pandas",
        "progressbar2",
        "numpy",
    ],
    author="Developer",
    description="A tool to streamline the process of downloading pre-trained word vectors.",
    python_requires=">=3.6",
)
