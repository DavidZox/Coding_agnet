import os
import sys

# Add the current directory to sys.path to ensure 'readtime' package can be found
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from readtime.api import of_text, of_html, of_markdown

def run_demo():
    # Define sample contents
    text_content = "The shortest blog post in the world!"
    html_content = "<html><body><h1>Hello</h1><p>This is <strong>HTML</strong> content.</p><img src='test.jpg'></body></html>"
    markdown_content = "## Markdown Title\nThis is **Markdown** content with an image: ![alt](img.png)"

    print("--- Reading Time Estimation Demo ---")

    # 1. Test Plain Text
    print("\n[1] Testing Plain Text:")
    res_text = of_text(text_content)
    print(f"Content: '{text_content}'")
    print(f"Result: {res_text}")
    print(f"Seconds: {res_text.seconds():.2f}")

    # 2. Test HTML
    print("\n[2] Testing HTML:")
    res_html = of_html(html_content)
    print(f"Content: '{html_content[:50]}...'")
    print(f"Result: {res_html}")
    print(f"Seconds: {res_html.seconds():.2f}")

    # 3. Test Markdown
    print("\n[3] Testing Markdown:")
    res_md = of_markdown(markdown_content)
    print(f"Content: '{markdown_content[:50]}...'")
    print(f"Result: {res_md}")
    print(f"Seconds: {res_md.seconds():.2f}")

    # 4. Test Custom WPM
    print("\n[4] Testing Custom WPM (WPM=5):")
    res_custom = of_text(text_content, wpm=5)
    print(f"Content: '{text_content}'")
    print(f"Result: {res_custom}")
    print(f"Seconds: {res_custom.seconds():.2f}")

    # 5. Test Operator Overloading (Addition)
    print("\n[5] Testing Operator Overloading (Result + Result):")
    r1 = of_text("Word " * 100) # approx 100 words
    r2 = of_text("Word " * 200) # approx 200 words
    r3 = r1 + r2
    print(f"R1: {r1.text()} ({r1.seconds():.2f}s)")
    print(f"R2: {r2.text()} ({r2.seconds():.2f}s)")
    print(f"R1 + R2: {r3.text()} ({r3.seconds():.2f}s)")

if __name__ == "__main__":
    run_demo()
