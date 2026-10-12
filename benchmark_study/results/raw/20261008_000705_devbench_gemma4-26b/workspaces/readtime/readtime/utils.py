from bs4 import BeautifulSoup
import markdown2
from readtime.result import Result

def parse_html(el):
    """
    Parse an HTML element and extract text and image information.
    
    :param el: The BeautifulSoup element to parse.
    :return: A tuple containing (text, image_count).
    """
    text = el.get_text()
    images = el.find_all('img')
    image_count = len(images)
    return text, image_count

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
    
    # Time for images: Assuming each image adds a certain amount of time.
    # A common heuristic is 10 seconds per image, but since the spec doesn't 
    # explicitly define the image constant, we'll use a standard approach 
    # or ensure it's part of the calculation. 
    # Based on typical reading time implementations:
    image_seconds = images * 10
    
    return text_seconds + image_seconds

def read_time(content, format, wpm=265):
    """
    Calculate the estimated reading time for the given content.
    
    :param content: The content string.
    :param format: The format of the content ('text', 'html', 'markdown').
    :param wpm: Words per minute.
    :return: A Result object.
    """
    if format == 'text':
        text = content
        images = 0
    elif format == 'html':
        soup = BeautifulSoup(content, 'lxml')
        text, images = parse_html(soup)
    elif format == 'markdown':
        # Convert markdown to HTML first to handle images and text extraction
        html_content = markdown2.markdown(content)
        soup = BeautifulSoup(html_content, 'lxml')
        text, images = parse_html(soup)
    else:
        raise ValueError(f"Unsupported format: {format}")

    seconds = read_time_as_seconds(text, images, wpm)
    return Result(seconds, wpm)
