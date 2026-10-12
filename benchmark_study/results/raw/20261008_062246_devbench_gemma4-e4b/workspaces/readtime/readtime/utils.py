from bs4 import BeautifulSoup, Tag
from typing import Tuple, List, Dict

# Define a structure for image information, although the exact structure is not specified,
# we adhere to the requirement to reserve space for it.
ImageInfo = Dict[str, str]

def parse_html(el: Tag) -> Tuple[str, List[ImageInfo]]:
    """
    Parse an HTML element and extract text content and image information.

    Args:
        el: The BeautifulSoup Tag object representing the HTML element.

    Returns:
        A tuple containing (extracted_text: str, images: List[ImageInfo]).
    """
    text_content = el.get_text(separator=' ', strip=True)
    images: List[ImageInfo] = []

    # Find all img tags within the element
    for img in el.find_all('img'):
        # Store basic image info (e.g., source and alt text)
        images.append({
            "src": img.get('src', ''),
            "alt": img.get('alt', '')
        })

    return text_content, images

def read_time_as_seconds(text: str, images: List[ImageInfo], wpm: int = 265) -> float:
    """
    Calculate the estimated reading time in seconds for a given text and images.

    Args:
        text: The plain text content.
        images: A list of image information dictionaries.
        wpm: The words per minute rate. Defaults to 265.

    Returns:
        The total estimated reading time in seconds.
    """
    # Estimate word count based on space separation
    word_count = len(text.split())

    # Time per word = 60 / WPM
    time_per_word_seconds = 60.0 / wpm

    # Base time for text
    text_time_seconds = word_count * time_per_word_seconds

    # Placeholder for image time estimation. Since no specific rule is given,
    # we assume a fixed time cost per image (e.g., 5 seconds per image).
    # This is a necessary assumption to fulfill the signature requirement.
    IMAGE_TIME_COST_SECONDS = 5.0
    image_time_seconds = len(images) * IMAGE_TIME_COST_SECONDS

    total_seconds = text_time_seconds + image_time_seconds
    return total_seconds

def read_time(content: str, format: str, wpm: int = 265) -> float:
    """
    Calculate the estimated reading time for the given content based on its format.

    Args:
        content: The content string (text, HTML, or markdown).
        format: The format of the content ('text', 'html', or 'markdown').
        wpm: The words per minute rate. Defaults to 265.

    Returns:
        The total estimated reading time in seconds.

    Raises:
        ValueError: If the format is unsupported.
    """
    if format == 'text':
        # For plain text, we treat it as text content and have no images initially
        return read_time_as_seconds(content, [], wpm)
    
    elif format == 'html':
        # For HTML, we need to parse it to extract text and images
        try:
            # Use BeautifulSoup to parse the HTML content
            soup = BeautifulSoup(content, 'lxml')
            # Get the body or the root element to parse
            el = soup.find() or soup
            
            text_content, images = parse_html(el)
            
            # Calculate time using the extracted text and images
            return read_time_as_seconds(text_content, images, wpm)
        except Exception as e:
            # Handle parsing errors gracefully
            print(f"Error parsing HTML content: {e}")
            raise ValueError("Unsupported or invalid HTML format.") from e

    elif format == 'markdown':
        # For markdown, we treat it as text content (assuming markdown2 conversion happens elsewhere or we just count words)
        # For simplicity in this utility, we treat markdown content as raw text for word counting.
        # A full implementation would convert markdown to HTML/text first.
        return read_time_as_seconds(content, [], wpm)
    
    else:
        raise ValueError(f"Unsupported content format: {format}. Must be 'text', 'html', or 'markdown'.")

# Note: read_time_as_seconds is the core calculation function, and read_time uses it.
# parse_html is specialized for HTML extraction.
