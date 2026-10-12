import os
from bs4 import BeautifulSoup
import markdown2

def analyze_file(filepath):
    print(f"--- Analyzing: {filepath} ---")
    if not os.path.exists(filepath):
        print(f"Error: {filepath} not found.")
        return

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    if filepath.endswith('.html'):
        soup = BeautifulSoup(content, 'lxml')
        text = soup.get_text()
        images = soup.find_all('img')
        num_images = len(images)
        print(f"Format: HTML")
        print(f"Raw text length: {len(text)}")
        print(f"Words (split()): {len(text.split())}")
        print(f"Words (split(' ')): {len(text.split(' '))}")
        print(f"Images found: {num_images}")

    elif filepath.endswith('.md'):
        # Convert markdown to HTML to see how it's parsed
        html_content = markdown2.markdown(content)
        soup = BeautifulSoup(html_content, 'lxml')
        text = soup.get_text()
        images = soup.find_all('img')
        num_images = len(images)
        print(f"Format: Markdown")
        print(f"Words (split()): {len(text.split())}")
        print(f"Images found: {num_images}")

    elif filepath.endswith('.txt'):
        text = content
        print(f"Format: Plain Text")
        print(f"Words (split()): {len(text.split())}")
        print(f"Words (split(' ')): {len(text.split(' '))}")

if __name__ == "__main__":
    samples_dir = 'samples'
    if os.path.exists(samples_dir):
        for filename in os.listdir(samples_dir):
            analyze_file(os.path.join(samples_dir, filename))
    else:
        print("Samples directory not found.")
