from bs4 import BeautifulSoup
from .result import Result

def parse_html(el) -> tuple[str, int]:
    """
    Parse an HTML element and extract text and image information.

    Args:
        el: A BeautifulSoup element.

    Returns:
        A tuple containing (extracted_text, image_count).
    """
    text_content = el.get_text(separator=' ', strip=True)
    image_count = el.find_all('img')
    return text_content, len(image_count)

def read_time(content, format, wpm) -> Result:
    """
    Calculate the estimated reading time for the given content.

    Args:
        content: The content string (text, HTML, or markdown).
        format: The format of the content ('text', 'html', or 'markdown').
        wpm: Words Per Minute rate.

    Returns:
        A Result object containing the reading time.
    """
    word_count = 0
    
    if format == 'text':
        # Simple word count for plain text
        word_count = len(content.split())
    
    elif format == 'html':
        # Parse HTML content
        soup = BeautifulSoup(content, 'lxml')
        el = soup.find()
        text, image_count = parse_html(el)
        
        # For HTML, we count words from extracted text. 
        # We assume image count is handled separately or implicitly by the calculation logic if needed, 
        # but for word count here, we use the text.
        word_count = len(text.split())
        
        # Following the structure, we calculate time based on words for now.
        # If we strictly follow the sequence diagram flow (which suggests Result.__init__ takes seconds and wpm),
        # we calculate seconds based on word count: (word_count / wpm) * 60
        seconds = (word_count / wpm) * 60
        return Result(seconds=seconds, wpm=wpm)

    elif format == 'markdown':
        # Simple word count for markdown (similar to plain text)
        word_count = len(content.split())
        seconds = (word_count / wpm) * 60
        return Result(seconds=seconds, wpm=wpm)
        
    else:
        raise ValueError(f"Unsupported content format: {format}")

    # For 'text' format, calculate seconds and return Result
    seconds = (word_count / wpm) * 60
    return Result(seconds=seconds, wpm=wpm)


def read_time_as_seconds(text: str, images: int, wpm: int) -> Result:
    """
    Calculate the estimated reading time in seconds for a given text and image count.

    Args:
        text: The text content.
        images: The number of images.
        wpm: Words Per Minute rate.

    Returns:
        A Result object containing the total reading time in seconds.
    """
    # Word count from text
    word_count = len(text.split())
    
    # Time for text: (word_count / wpm) * 60 seconds/minute
    text_time_seconds = (word_count / wpm) * 60
    
    # Time for images: 5 seconds per image (as per requirement description)
    image_time_seconds = images * 5
    
    total_seconds = text_time_seconds + image_time_seconds
    
    return Result(seconds=total_seconds, wpm=wpm)
