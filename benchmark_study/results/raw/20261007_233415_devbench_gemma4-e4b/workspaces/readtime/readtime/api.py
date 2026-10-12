from readtime.utils import read_time, parse_html
from readtime.result import Result

def of_text(text: str, wpm: int) -> Result:
    """
    Calculate the reading time of a given plain text.

    :param text: The plain text content.
    :param wpm: Words Per Minute rate.
    :return: A Result object containing the estimated reading time.
    """
    return read_time(text, 'text', wpm)

def of_html(html: str, wpm: int) -> Result:
    """
    Calculate the reading time of an HTML document.

    :param html: The HTML content string.
    :param wpm: Words Per Minute rate.
    :return: A Result object containing the estimated reading time.
    """
    # Based on the requirement: "For of_html, need to first use readtime.utils.parse_html 
    # to get text and image info, then pass the result to read_time."
    # We assume parse_html(html) returns the necessary content structure that read_time expects 
    # when format is 'html'.
    parsed_data = parse_html(html)
    return read_time(parsed_data, 'html', wpm)


def of_markdown(markdown: str, wpm: int) -> Result:
    """
    Calculate the reading time of a given markdown text.

    :param markdown: The markdown content string.
    :param wpm: Words Per Minute rate.
    :return: A Result object containing the estimated reading time.
    """
    return read_time(markdown, 'markdown', wpm)
