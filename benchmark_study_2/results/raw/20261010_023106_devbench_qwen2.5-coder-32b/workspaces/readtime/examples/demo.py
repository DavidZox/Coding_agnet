import sys
import os

# Add the project root to the sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from readtime import of_text, of_html, of_markdown

# Example usage of of_text
text_content = "The shortest blog post in the world!"
text_result = of_text(text_content)
print(f"Reading time for text: {text_result}")

# Example usage of of_html
html_content = "<p>This is a <strong>sample</strong> HTML content.</p>"
html_result = of_html(html_content)
print(f"Reading time for HTML: {html_result}")

# Example usage of of_markdown
markdown_content = "This is a **sample** markdown content."
markdown_result = of_markdown(markdown_content)
print(f"Reading time for markdown: {markdown_result}")
