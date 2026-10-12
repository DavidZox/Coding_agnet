from bs4 import BeautifulSoup
import markdown2
from readtime.result import Result

def parse_html(el):
    """
    Parse an HTML element and extract text and image information.
    
    :param el: The BeautifulSoup element to parse.
    :return: A tuple of (text, image_count).
    """
    text = el.get_text()
    images = el.find_all('img')
    return text, len(images)

def read_time_as_seconds(text, images, wpm=265):
    """
    Calculate the estimated reading time in seconds for a given text and image count.
    
    :param text: The plain text content.
    :param images: The number of images.
    :param wpm: Words per minute.
    :return: Total seconds.
    """
    # Calculate words. A simple split is used for word count.
    words = text.split()
    word_count = len(words)
    
    # Time for text: (words / wpm) * 60 seconds
    text_seconds = (word_count / wpm) * 60
    
    # Time for images: Assume each image takes 2 seconds (standard estimation)
    image_seconds = images * 2
    
    return text_seconds + image_seconds

def read_time(content, format, wpm=265):
    """
    Calculate the estimated reading time for the given content.
    
    :param content: The content string.
    :param format: The format of the content ('text', 'html', 'markdown').
    :param wpm: Words per minute.
    :return: A Result object.
    :raises ValueError: If the format is unsupported.
    """
    if format == 'text':
        # For plain text, we treat it as text with 0 images
        seconds = read_time_as_seconds(content, 0, wpm)
        return Result(seconds, wpm)
    
    elif format == 'html':
        soup = BeautifulSoup(content, 'lxml')
        text, img_count = parse_html(soup)
        seconds = read_time_as_seconds(text, img_count, wpm)
        return Result(seconds, wpm)
    
    elif format == 'markdown':
        # Convert markdown to HTML to use the same parsing logic
        html_content = markdown2.markdown(content)
        soup = BeautifulSoup(html_content, 'lxml')
        text, img_count = parse_html(soup)
        seconds = read_time_as_seconds(text, img_count, wpm)
        return Result(seconds, wpm)
    
    else:
        raise ValueError(f"Unsupported format: {format}")
