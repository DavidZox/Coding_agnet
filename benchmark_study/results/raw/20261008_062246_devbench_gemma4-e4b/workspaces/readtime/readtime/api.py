from .utils import read_time, read_time_as_seconds
from .result import Result

class Global_functions:
    """
    A class to host global functions related to reading time calculation.
    """

    @staticmethod
    def of_text(text: str, wpm: int = 265) -> Result:
        """
        Calculate the reading time of a given plain text.

        :param text: The plain text content.
        :param wpm: Words Per Minute rate. Defaults to 265.
        :return: A Result object containing the estimated reading time.
        """
        # Based on UML sequence diagram, this calls read_time(text, 'text', wpm)
        return read_time(text, 'text', wpm)

    @staticmethod
    def of_html(html: str, wpm: int = 265) -> Result:
        """
        Calculate the reading time of an HTML document.

        :param html: The HTML content string.
        :param wpm: Words Per Minute rate. Defaults to 265.
        :return: A Result object containing the estimated reading time.
        """
        # Based on UML sequence diagram, this calls read_time(html, 'html', wpm)
        return read_time(html, 'html', wpm)

    @staticmethod
    def of_markdown(markdown: str, wpm: int = 265) -> Result:
        """
        Calculate the reading time of a markdown text.

        :param markdown: The markdown content string.
        :param wpm: Words Per Minute rate. Defaults to 265.
        :return: A Result object containing the estimated reading time.
        """
        # Based on UML sequence diagram, this calls read_time(markdown, 'markdown', wpm)
        return read_time(markdown, 'markdown', wpm)

    @staticmethod
    def read_time(content, format: str, wpm: int = 265) -> Result:
        """
        Calculate the estimated reading time for the given content and format.

        :param content: The content string (text, HTML, or markdown).
        :param format: The format of the content ('text', 'html', 'markdown').
        :param wpm: Words Per Minute rate. Defaults to 265.
        :return: A Result object containing the estimated reading time.
        """
        # This delegates to utils.py's core logic
        return read_time(content, format, wpm)

    @staticmethod
    def read_time_as_seconds(text: str, images: list = None, wpm: int = 265) -> Result:
        """
        Calculate the estimated reading time in seconds for a given text, optionally considering images.

        :param text: The text content.
        :param images: A list of image counts/data (implementation detail might vary).
        :param wpm: Words Per Minute rate. Defaults to 265.
        :return: A Result object containing the estimated reading time.
        """
        # This delegates to utils.py's specific function
        return read_time_as_seconds(text, images, wpm)
