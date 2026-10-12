from bs4 import BeautifulSoup
import markdown2
from readtime.result import Result

def parse_html(el):
    """
    Parse an HTML element and extract text and image information.
    
    :param el: The HTML element (can be a string or a BeautifulSoup object)
    :return: A tuple of (text, image_count)
    """
    if isinstance(el, str):
        soup = BeautifulSoup(el, 'lxml')
    else:
        soup = el

    # Extract text
    text = soup.get_text()
    
    # Extract image count
    images = soup.find_all('img')
    image_count = len(images)
    
    return text, image_count

def read_time_as_seconds(text, images, wpm=265):
    """
    Calculate the estimated reading time in seconds for a given text and image count.
    
    :param text: The plain text content
    :param images: The number of images
    :param wpm: Words per minute
    :return: Total seconds
    """
    # Calculate words. A simple split is used for word count.
    words = text.split()
    word_count = len(words)
    
    # Calculate seconds from words
    # (word_count / wpm) * 60
    seconds_from_words = (word_count / wpm) * 60
    
    # Assume each image adds a certain amount of reading time (e.g., 10 seconds)
    # However, the prompt doesn't specify the exact constant for images.
    # Based on common reading time logic, we'll add 10 seconds per image.
    seconds_from_images = images * 10
    
    return seconds_from_words + seconds_from_images

def read_time(content, format, wpm=265):
    """
    Calculate the estimated reading time for the given content.
    
    :param content: The content string
    :param format: 'text', 'html', or 'markdown'
    :param wpm: Words per minute
    :return: A Result object
    """
    if format == 'text':
        text = content
        images = 0
    elif format == 'html':
        text, images = parse_html(content)
    elif format == 'markdown':
        # Convert markdown to HTML to extract text and images correctly
        html_content = markdown2.markdown(content)
        text, images = parse_html(html_content)
    else:
        raise ValueError(f"Unsupported format: {format}")

    total_seconds = read_time_as_seconds(text, images, wpm)
    return Result(total_seconds, wpm)
