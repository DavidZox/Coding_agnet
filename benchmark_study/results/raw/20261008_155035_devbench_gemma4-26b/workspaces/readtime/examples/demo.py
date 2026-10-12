import sys
import os

# Add the current directory to sys.path to allow importing 'readtime'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from readtime.api import of_text, of_html, of_markdown

def main():
    # Test Plain Text
    print("Testing Plain Text:")
    text_content = "The shortest blog post in the world!"
    text_result = of_text(text_content)
    print(f"Content: '{text_content}'")
    print(f"Result: {text_result}")
    print(f"Seconds: {text_result.seconds()}")
    print(f"Minutes: {text_result.minutes()}")
    print("-" * 20)

    # Test HTML
    print("Testing HTML:")
    html_content = "This is <strong>HTML</strong> content with an <img src='test.jpg'> image."
    html_result = of_html(html_content)
    print(f"Content: '{html_content}'")
    print(f"Result: {html_result}")
    print(f"Seconds: {html_result.seconds()}")
    print(f"Minutes: {html_result.minutes()}")
    print("-" * 20)

    # Test Markdown
    print("Testing Markdown:")
    md_content = "This is **Markdown** content."
    md_result = of_markdown(md_content)
    print(f"Content: '{md_content}'")
    print(f"Result: {md_result}")
    print(f"Seconds: {md_result.seconds()}")
    print(f"Minutes: {md_result.minutes()}")
    print("-" * 20)

    # Test Custom WPM
    print("Testing Custom WPM (5 WPM):")
    custom_wpm_result = of_text(text_content, wpm=5)
    print(f"Content: '{text_content}' (WPM=5)")
    print(f"Result: {custom_wpm_result}")
    print(f"Seconds: {custom_wpm_result.seconds()}")
    print("-" * 20)

if __name__ == "__main__":
    main()
