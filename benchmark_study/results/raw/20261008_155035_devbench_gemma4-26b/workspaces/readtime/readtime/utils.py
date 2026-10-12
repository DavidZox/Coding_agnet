import markdown2
from bs4 import BeautifulSoup
from readtime.result import Result

def parse_html(el):
    """
    Parse an HTML element and extract text and image information.
    
    :param el: BeautifulSoup element
    :return: tuple (text, image_count)
    """
    text = el.get_text()
    images = el.find_all('img')
    image_count = len(images)
    return text, image_count

def read_time_as_seconds(text, images, wpm=265):
    """
    Calculate the estimated reading time in seconds for a given text and image count.
    
    :param text: The plain text content
    :param images: The number of images
    :param wpm: Words per minute
    :return: total seconds as float
    """
    # Count words by splitting whitespace
    word_count = len(text.split())
    
    # Calculate seconds based on WPM
    # WPM = words / minutes => minutes = words / WPM
    # seconds = (words / WPM) * 60
    text_seconds = (word_count / wpm) * 60 if wpm > 0 else 0
    
    # Assume each image adds a fixed amount of reading time (e.g., 10 seconds)
    # This is a common heuristic for reading time calculators
    image_seconds = images * 10
    
    return text_seconds + image_seconds

def read_time(content, format, wpm=265):
    """
    Calculate the estimated reading time for the given content.
    
    :param content: The content string
    :param format: 'text', 'html', or 'markdown'
    :param wpm: Words per minute
    :return: Result object
    """
    if format == 'text':
        text = content
        image_count = 0
    elif format == 'html':
        soup = BeautifulSoup(content, 'lxml')
        text, image_count = parse_html(soup)
    elif format == 'markdown':
        # Convert markdown to HTML first
        html_content = markdown2.markdown(content)
        soup = BeautifulSoup(html_content, 'lxml')
        text, image_count = parse_html(soup)
    else:
        raise ValueError(f"Unsupported format: {format}")

    total_seconds = read_time_as_seconds(text, image_count, wpm)
    return Result(total_seconds, wpm)
