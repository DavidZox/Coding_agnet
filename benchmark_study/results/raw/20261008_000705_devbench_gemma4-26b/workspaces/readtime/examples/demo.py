import sys
import os

# Add the current directory to sys.path to ensure 'readtime' package can be found
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from readtime.api import of_text, of_html, of_markdown

def main():
    # Test plain text
    text_content = "The shortest blog post in the world!"
    text_result = of_text(text_content)
    print(f"Text: {text_content}")
    print(f"Result: {text_result} ({text_result.seconds:.2f} seconds)")

    # Test HTML
    html_content = "<html><body><h1>Hello</h1><p>This is <strong>HTML</strong> content.</p><img src='test.jpg'></body></html>"
    html_result = of_html(html_content)
    print(f"\nHTML: {html_content}")
    print(f"Result: {html_result} ({html_result.seconds:.2f} seconds)")

    # Test Markdown
    md_content = "# Markdown Title\nThis is **Markdown** content with an image: ![alt](img.png)"
    md_result = of_markdown(md_content)
    print(f"\nMarkdown: {md_content}")
    print(f"Result: {md_result} ({md_result.seconds:.2f} seconds)")

    # Test custom WPM
    custom_wpm_result = of_text(text_content, wpm=5)
    print(f"\nCustom WPM (5): {text_content}")
    print(f"Result: {custom_wpm_result} ({custom_wpm_result.seconds:.2f} seconds)")

if __name__ == "__main__":
    main()
