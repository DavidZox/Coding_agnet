from bs4 import BeautifulSoup
import markdown2
from readtime.result import Result

def parse_html(el):
    """
    Parse an HTML element and extract text and image information.
    Returns a tuple of (text, image_count).
    """
    text = el.get_text()
    images = el.find_all('img')
    return text, len(images)

def read_time_as_seconds(text, images, wpm=265):
    """
    Calculate the estimated reading time in seconds for a given text and image count.
    """
    # Calculate word count. A simple split is used for text.
    words = text.split()
    word_count = len(words)
    
    # Time for text: (words / wpm) * 60 seconds
    text_seconds = (word_count / wpm) * 60
    
    # Time for images: Assuming each image adds a constant amount of time.
    # Since the PRD doesn't specify, we follow a common convention of 12 seconds per image.
    image_seconds = images * 12
    
    return int(text_seconds + image_seconds)

def read_time(content, format, wpm=265):
    """
    Calculate the estimated reading time for the given content based on format.
    Returns a Result object.
    """
    if format == 'text':
        words = content.split()
        word_count = len(words)
        seconds = int((word_count / wpm) * 60)
        return Result(seconds, wpm)
    
    elif format == 'html':
        soup = BeautifulSoup(content, 'lxml')
        text, image_count = parse_html(soup)
        seconds = read_time_as_seconds(text, image_count, wpm)
        return Result(seconds, wpm)
    
    elif format == 'markdown':
        # Convert markdown to HTML first
        html_content = markdown2.markdown(content)
        soup = BeautifulSoup(html_content, 'lxml')
        text, image_count = parse_html(soup)
        seconds = read_time_as_seconds(text, image_count, wpm)
        return Result(seconds, wpm)
    
    else:
        raise ValueError(f"Unsupported format: {format}")
