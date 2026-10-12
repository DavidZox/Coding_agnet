from .utils import read_time
from .result import Result

def of_text(text: str, wpm: int = 265) -> Result:
    """
    Calculate the reading time of a given plain text.

    :param text: The plain text content.
    :param wpm: Words Per Minute rate.
    :return: Result object containing reading time.
    """
    return read_time(text, 'text', wpm)

def of_html(html: str, wpm: int = 265) -> Result:
    """
    Calculate the reading time of an HTML document.

    :param html: The HTML content.
    :param wpm: Words Per Minute rate.
    :return: Result object containing reading time.
    """
    # In a real implementation, utils.py would handle parsing the HTML
    # and extracting text/image info before calling read_time.
    # Following the architecture, we pass the raw HTML and let utils handle the format.
    return read_time(html, 'html', wpm)

def of_markdown(markdown: str, wpm: int = 265) -> Result:
    """
    Calculate the reading time of a markdown text.

    :param markdown: The markdown content.
    :param wpm: Words Per Minute rate.
    :return: Result object containing reading time.
    """
    # In a real implementation, utils.py would handle parsing the markdown.
    return read_time(markdown, 'markdown', wpm)
