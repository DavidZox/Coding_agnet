#!/bin/bash

# Make sure to activate your Python environment if needed
# source /path/to/your/virtualenv/bin/activate

# Usage example for searching word vectors for English language
echo "Searching for English word vectors..."
python -c "import chakin; print(chakin.search(lang='Arabic'))"

# Example usage for downloading a specific word vector by number
# Here number '1' is an example, replace it with the actual number for the desired word vector
echo "Downloading the fastText English word vector..."
# python -c "import chakin; chakin.download(number=1, save_dir='./outputs/downloaded_vectors')"

# Deactivate your Python environment if needed
# deactivate
