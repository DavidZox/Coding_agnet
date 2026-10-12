import os
import sys

# Add the current directory to sys.path to ensure 'readtime' package can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import readtime.api as api

def main():
    # Define paths to sample files
    samples_dir = 'samples'
    html_file = os.path.join(samples_dir, 'html.html')
    markdown_file = os.path.join(samples_dir, 'markdown.md')
    text_file = os.path.join(samples_dir, 'plain_text.txt')

    print("--- ReadTime Demo ---")

    # 1. Test Plain Text
    if os.path.exists(text_file):
        with open(text_file, 'r', encoding='utf-8') as f:
            content = f.read()
        result = api.of_text(content)
        print(f"Plain Text: {result}")
    else:
        print("Plain Text sample not found.")

    # 2. Test HTML
    if os.path.exists(html_file):
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()
        result = api.of_html(content)
        print(f"HTML: {result}")
    else:
        print("HTML sample not found.")

    # 3. Test Markdown
    if os.path.exists(markdown_file):
        with open(markdown_file, 'r', encoding='utf-8') as f:
            content = f.read()
        result = api.of_markdown(content)
        print(f"Markdown: {result}")
    else:
        print("Markdown sample not found.")

    # 4. Test Custom WPM
    print("\n--- Custom WPM (5 WPM) ---")
    custom_text = "The shortest blog post in the world!"
    result_custom = api.of_text(custom_text, wpm=5)
    print(f"Custom WPM Result: {result_custom}")
    print(f"Seconds: {result_custom.seconds()}")
    print(f"Minutes: {result_custom.minutes():.2f}")

if __name__ == "__main__":
    main()
