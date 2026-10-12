#!/bin/bash

# Make sure to activate your Python environment if needed
# source /path/to/your/virtualenv/bin/activate

# Ensure the requests package is installed
# You can install it using: pip install requests
if ! python -c "import requests" &> /dev/null; then
    echo "The requests package is not installed. Please install it using: pip install requests"
    exit 1
fi

# Usage example for searching word vectors for English language
echo "Searching for English word vectors..."
python -c "import chakin; print(chakin.search(lang='English'))"

# Example usage for downloading a specific word vector by number
# Here number '2' is an example, replace it with the actual number for the desired word vector
echo "Downloading the fastText English word vector..."
python -c "import chakin; chakin.download(number=2, save_dir='./')"

# Deactivate your Python environment if needed
# deactivate
