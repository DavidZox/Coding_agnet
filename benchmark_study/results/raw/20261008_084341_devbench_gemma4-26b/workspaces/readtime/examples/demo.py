import sys
import os

# Add the parent directory to sys.path to ensure 'readtime' package can be found
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from readtime import of_text, of_html, of_markdown

def main():
    # Test plain text
    text_content = "The shortest blog post in the world!"
    text_result = of_text(text_content)
    print(f"Text: '{text_content}'")
    print(f"Reading time: {text_result}")
    print(f"Seconds: {text_result.seconds}")
    print("-" * 20)

    # Test HTML
    html_content = "<html><body><h1>Hello</h1><p>This is <strong>HTML</strong> content.</p><img src='test.jpg'></body></html>"
    html_result = of_html(html_content)
    print(f"HTML content: {html_content}")
    print(f"Reading time: {html_result}")
    print(f"Seconds: {html_result.seconds}")
    print("-" * 20)

    # Test Markdown
    md_content = "# Title\nThis is **Markdown** content."
    md_result = of_markdown(md_content)
    print(f"Markdown content: {md_content}")
    print(f"Reading time: {md_result}")
    print(f"Seconds: {md_result.seconds}")
    print("-" * 20)

    # Test custom WPM
    custom_wpm_result = of_text(text_content, wpm=5)
    print(f"Text with custom WPM (5): '{text_content}'")
    print(f"Reading time: {custom_wpm_result}")
    print(f"Seconds: {custom_wpm_result.seconds}")

if __name__ == "__main__":
    main()
