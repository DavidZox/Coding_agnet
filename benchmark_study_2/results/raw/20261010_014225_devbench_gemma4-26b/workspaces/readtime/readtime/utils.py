import markdown2
from bs4 import BeautifulSoup
from readtime.result import Result

def parse_html(el):
    """
    Parse an HTML element and extract text and image information.
    
    :param el: The HTML element (as a string or BeautifulSoup object)
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
    :return: Total seconds as a float
    """
    # Count words (splitting by whitespace)
    word_count = len(text.split())
    
    # Calculate seconds for text: (words / wpm) * 60
    text_seconds = (word_count / wpm) * 60
    
    # Assume each image adds a constant amount of reading time (e.g., 10 seconds)
    # This is a common heuristic for reading time calculators
    image_seconds = images * 10
    
    return text_seconds + image_seconds

def read_time(content, format, wpm=265):
    """
    Calculate the estimated reading time for the given content based on format.
    
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
        # Convert markdown to HTML first to handle images and text extraction consistently
        html_content = markdown2.markdown(content)
        text, images = parse_html(html_content)
    else:
        raise ValueError(f"Unsupported format: {format}")

    seconds = read_time_as_seconds(text, images, wpm)
    return Result(seconds, wpm)
