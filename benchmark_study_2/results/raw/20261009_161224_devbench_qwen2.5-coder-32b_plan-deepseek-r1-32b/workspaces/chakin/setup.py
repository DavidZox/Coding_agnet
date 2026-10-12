from setuptools import setup, find_packages

with open('requirements.txt') as f:
    required = f.read().splitlines()

setup(
    name='chakin',
    version='0.1.0',
    packages=find_packages(),
    install_requires=required,
    author='Your Name',
    author_email='your.email@example.com',
    description='A tool to download pre-trained word vectors for NLP tasks',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/yourusername/chakin',
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6',
)
