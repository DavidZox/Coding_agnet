from .result import Result
from bs4 import BeautifulSoup
import markdown2
import re

def parse_html(el):
    """
    Parse an HTML element and extract text and image information.

    Args:
        el: A BeautifulSoup Tag object representing the HTML element.

    Returns:
        tuple: A tuple containing (text_content, image_data).
               image_data is a list of image sources (str).
    """
    text_content = el.get_text(separator=' ', strip=True)
    image_data = []
    for img in el.find_all('img'):
        src = img.get('src')
        if src:
            image_data.append(src)
    return text_content, image_data

def read_time(content, format, wpm=265):
    """
    Calculate the estimated reading time for the given content.

    Args:
        content: The content string (text, HTML, or markdown).
        format: The format of the content ('text', 'html', or 'markdown').
        wpm: The words per minute rate.

    Returns:
        Result: An object representing the calculated reading time.

    Raises:
        ValueError: If the format is unsupported.
    """
    text_content = ""
    images = []

    if format == 'text':
        text_content = content
    elif format == 'html':
        soup = BeautifulSoup(content, 'lxml')
        el = soup.find('body')
        if el:
            text_content, images = parse_html(el)
        else:
            text_content = content # Fallback if body not found
    elif format == 'markdown':
        # Convert markdown to HTML first to get clean text representation
        html_content = markdown2.markdown(content)
        soup = BeautifulSoup(html_content, 'lxml')
        el = soup.find('body')
        if el:
            text_content, images = parse_html(el)
        else:
            # If parsing fails, use the raw markdown content as a fallback text
            text_content = content
    else:
        raise ValueError(f"Unsupported content format: {format}")

    # Calculate reading time using the dedicated function
    return read_time_as_seconds(text_content, images, wpm)

def read_time_as_seconds(text, images, wpm=265):
    """
    Calculate the estimated reading time in seconds for a given text and images.

    Args:
        text: The plain text content.
        images: A list of image sources (strings).
        wpm: The words per minute rate.

    Returns:
        Result: An object representing the calculated reading time.
    """
    # Simple word count: split by whitespace
    word_count = len(text.split())
    
    # Estimate time based on words. Assume 1 word = 1 unit of reading time.
    # Time in minutes = word_count / WPM
    # Time in seconds = (word_count / WPM) * 60
    
    if wpm <= 0:
        raise ValueError("WPM must be a positive number.")
        
    time_in_seconds = (word_count / wpm) * 60
    
    # Note: The PRD mentions images, but the calculation logic provided in the prompt 
    # focuses on word count. We will use the word count for the primary calculation.
    # If image time estimation were required, it would be added here.
    
    return Result(seconds=time_in_seconds, wpm=wpm)
