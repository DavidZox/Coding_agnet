from setuptools import setup, find_packages

setup(
    name='chakin',
    version='0.1.0',
    packages=find_packages(),
    install_requires=[
        'progressbar2',
        'numpy',
        'pandas',
    ],
    author='DevBench',
    description='A tool to streamline the process of downloading pre-trained word vectors.',
    python_requires='>=3.6',
)
