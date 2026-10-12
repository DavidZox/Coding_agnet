import sys
import os

# Add the project root to sys.path to ensure 'readtime' can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from readtime.api import of_text, of_html, of_markdown

def main():
    # Test plain text
    text_content = "The shortest blog post in the world!"
    text_result = of_text(text_content)
    print(f"Text content: '{text_content}'")
    print(f"Result: {text_result}")
    print(f"Seconds: {text_result.seconds()}, Minutes: {text_result.minutes()}, Text: {text_result.text()}")
    print("-" * 20)

    # Test HTML
    html_content = "<html><body><h1>Hello</h1><p>This is <strong>HTML</strong> content.</p></body></html>"
    html_result = of_html(html_content)
    print(f"HTML content: {html_content}")
    print(f"Result: {html_result}")
    print(f"Seconds: {html_result.seconds()}, Minutes: {html_result.minutes()}, Text: {html_result.text()}")
    print("-" * 20)

    # Test Markdown
    markdown_content = "# Title\nThis is **Markdown** content."
    md_result = of_markdown(markdown_content)
    print(f"Markdown content: {markdown_content}")
    print(f"Result: {md_result}")
    print(f"Seconds: {md_result.seconds()}, Minutes: {md_result.minutes()}, Text: {md_result.text()}")
    print("-" * 20)

    # Test custom WPM
    custom_wpm_result = of_text(text_content, wpm=5)
    print(f"Text content with WPM=5: '{text_content}'")
    print(f"Result: {custom_wpm_result}")
    print(f"Seconds: {custom_wpm_result.seconds()}, Minutes: {custom_wpm_result.minutes()}, Text: {custom_wpm_result.text()}")

if __name__ == "__main__":
    main()
