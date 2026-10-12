import re
from bs4 import BeautifulSoup
from markdown2 import markdown
from readtime.result import Result

def parse_html(el):
    """
    parse an HTML element and extract text and image information.
    """
    text = el.get_text()
    images = el.find_all('img')
    image_count = len(images)
    return text, image_count

def read_time_as_seconds(text, images, wpm):
    """
    calculate the estimated reading time in seconds for a given text.
    """
    # Standard word count calculation
    words = re.findall(r'\w+', text)
    word_count = len(words)
    
    # Calculate base seconds from words
    # WPM to seconds: 60 / WPM per word
    seconds_per_word = 60.0 / wpm
    total_seconds = word_count * seconds_per_word
    
    # Add time for images (e.g., 2 seconds per image as a heuristic)
    total_seconds += (images * 2)
    
    return total_seconds

def read_time(content, format, wpm):
    """
    calculate the estimated reading time for the given content.
    """
    if format == 'text':
        text = content
        images = 0
    elif format == 'html':
        soup = BeautifulSoup(content, 'lxml')
        text, images = parse_html(soup)
    elif format == 'markdown':
        # Convert markdown to HTML to use the same parsing logic
        html_content = markdown(content)
        soup = BeautifulSoup(html_content, 'lxml')
        text, images = parse_html(soup)
    else:
        raise ValueError(f"Unsupported format: {format}")

    seconds = read_time_as_seconds(text, images, wpm)
    return Result(seconds, wpm)
