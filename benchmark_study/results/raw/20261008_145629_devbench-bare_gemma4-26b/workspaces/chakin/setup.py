from setuptools import setup, find_packages

setup(
    name="chakin",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "pandas",
        "requests",
        "progressbar2",
        "six",
    ],
    author="DevBench",
    description="A tool to download pre-trained word vectors.",
    python_requires=">=3.6",
)
