from bs4 import BeautifulSoup
from markdown2 import markdown
from typing import Tuple, Dict, Any

def read_time(content: str, format: str, wpm: int) -> 'Result':
    """
    calculate the estimated reading time for the given content.

    :param content: The content string (text, HTML, or markdown).
    :type content: str
    :param format: The format of the content ('text', 'html', or 'markdown').
    :type format: str
    :param wpm: Words Per Minute rate.
    :type wpm: int
    :return: Result object containing reading time.
    :rtype: Result
    :raises ValueError: If the format is unsupported.
    """
    if format == 'text':
        text_content = content
    elif format == 'html':
        text_content, images = parse_html(content)
    elif format == 'markdown':
        # Convert markdown to text first for word counting
        text_content = markdown(content)
        images = []
    else:
        raise ValueError(f"Unsupported content format: {format}")

    # Calculate word count based on text content
    word_count = len(text_content.split())

    # Use read_time_as_seconds to get the final Result object
    return read_time_as_seconds(text_content, images, wpm)

def read_time_as_seconds(text: str, images: list, wpm: int) -> 'Result':
    """
    calculate the estimated reading time in seconds for a given text, considering images.

    :param text: The plain text content.
    :type text: str
    :param images: A list of image counts or placeholders.
    :type images: list
    :param wpm: Words Per Minute rate.
    :type wpm: int
    :return: Result object containing reading time.
    :rtype: Result
    """
    # Simple estimation: assume 1 image takes 10 seconds extra reading time
    image_time_seconds = len(images) * 10
    
    # Calculate reading time based on words
    words = text.split()
    word_count = len(words)
    
    # Time in minutes = word_count / wpm
    # Time in seconds = (word_count / wpm) * 60
    reading_time_seconds = (word_count / wpm) * 60
    
    total_seconds = reading_time_seconds + image_time_seconds
    
    return Result(total_seconds, wpm)

def parse_html(el: str) -> Tuple[str, list]:
    """
    parse an HTML element and extract text and image information.

    :param el: The HTML content string.
    :type el: str
    :return: A tuple containing (extracted_text, image_list).
    :rtype: Tuple[str, list]
    """
    soup = BeautifulSoup(el, 'lxml')
    
    # Extract text content
    text_content = soup.get_text(separator=' ', strip=True)
    
    # Extract image information (count)
    image_list = []
    for img in soup.find_all('img'):
        # For simplicity, we count images as a placeholder in the list
        image_list.append(1) 
        
    return text_content, image_list
