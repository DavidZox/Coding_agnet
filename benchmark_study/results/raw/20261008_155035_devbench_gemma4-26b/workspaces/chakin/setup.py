from setuptools import setup

setup(
    name="chakin",
    version="0.1.0",
    packages=["chakin"],
    include_package_data=True,
    install_requires=[
        "progressbar2",
        "numpy",
        "pandas",
        "requests",
    ],
    author="DevBench",
    description="A tool to download pre-trained word vectors.",
    python_requires=">=3.6",
)
