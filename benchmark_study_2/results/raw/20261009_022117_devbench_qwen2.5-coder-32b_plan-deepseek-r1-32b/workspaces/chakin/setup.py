from setuptools import setup, find_packages

setup(
    name='chakin',
    version='0.1.0',
    packages=find_packages(),
    install_requires=[
        'setuptools',
        'progressbar2',
        'numpy',
        'pandas',
        'requests'
    ]
)
