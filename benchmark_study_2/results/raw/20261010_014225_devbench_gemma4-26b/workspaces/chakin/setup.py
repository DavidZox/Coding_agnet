from distutils.core import setup

setup(
    name="chakin",
    version="0.1.0",
    packages=["chakin"],
    install_requires=[
        "pandas",
        "progressbar2",
        "numpy",
    ],
    python_requires=">=3.6",
)
