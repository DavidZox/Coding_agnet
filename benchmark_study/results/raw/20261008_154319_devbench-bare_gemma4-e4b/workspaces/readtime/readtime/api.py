from .utils import read_time, read_time_as_seconds, parse_html
from .result import Result

def of_text(text: str, wpm: int = 265) -> Result:
    """
    calculate the reading time of a given text.

    :param text: The plain text content.
    :type text: str
    :param wpm: Words Per Minute rate. Defaults to 265.
    :type wpm: int
    :return: Result object containing reading time.
    :rtype: Result
    """
    return read_time(text, 'text', wpm)

def of_html(html: str, wpm: int = 265) -> Result:
    """
    calculate the reading time of an HTML document.

    :param html: The HTML content.
    :type html: str
    :param wpm: Words Per Minute rate. Defaults to 265.
    :type wpm: int
    :return: Result object containing reading time.
    :rtype: Result
    """
    # Assuming read_time handles HTML parsing internally or relies on utils.parse_html
    # Based on the description, we pass the raw HTML string.
    return read_time(html, 'html', wpm)

def of_markdown(markdown: str, wpm: int = 265) -> Result:
    """
    calculate the reading time of a markdown text.

    :param markdown: The markdown content.
    :type markdown: str
    :param wpm: Words Per Minute rate. Defaults to 265.
    :type wpm: int
    :return: Result object containing reading time.
    :rtype: Result
    """
    return read_time(markdown, 'markdown', wpm)
