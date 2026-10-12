"""
    readtime.utils
    ~~~~~~~~~~~~~~

    Utility and non-public methods.

    :copyright: (c) 2016 Alan Hamlett.
    :license: BSD, see LICENSE for more details.
"""



import math
import re

from .result import Result

DEFAULT_WPM = 265  # Medium says they use 275 WPM but they actually use 265
WORD_DELIMITER = re.compile(r'\W+')


def read_time(content, format=None, wpm=265):
    """
    Calculate the estimated reading time for the given content.

    Parameters:
        content (str): The content to calculate the reading time for.
        format (str, optional): The format of the content. Supported format is 'text'. Defaults to None.
        wpm (int, optional): The reading speed in words per minute. Defaults to None.

    Returns:
        Result: An instance of the Result class containing the calculated reading time in seconds and the reading speed in words per minute.
    
    Raises:
        Exception: If the specified format is not supported.
    """
    try:
        format = format.lower()
    except:
        pass

    if format == 'text':
        seconds = read_time_as_seconds(content, wpm=wpm)

    else:
        raise Exception(f'Unsupported format: {format}')

    return Result(seconds=seconds, wpm=wpm)


def read_time_as_seconds(text, images=0, wpm=265):
    """
    Calculate the estimated reading time in seconds for a given text.

    Parameters:
        text (str): The text to calculate the reading time for.
        images (int, optional): The number of inline images in the text. Defaults to 0.
        wpm (int, optional): The average reading speed in words per minute. Defaults to None.

    Returns:
        int: The estimated reading time in seconds.
    """

    try:
        num_words = len(re.split(WORD_DELIMITER, text.strip()))
    except (AttributeError, TypeError):
        num_words = 0

    seconds = math.ceil(num_words / wpm * 60)

    # add extra seconds for inline images
    delta = 12
    for _ in range(images):
        seconds += delta
        if delta > 3:
            delta -= 1

    return seconds
