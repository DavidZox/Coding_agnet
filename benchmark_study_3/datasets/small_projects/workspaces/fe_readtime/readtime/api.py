"""
    readtime.api
    ~~~~~~~~~~~~

    Contains public methods.

    :copyright: (c) 2016 Alan Hamlett.
    :license: BSD, see LICENSE for more details.
"""


from . import utils


def of_text(text, wpm=265):
    """
    Calculate the reading time of a given text.

    Parameters:
        text (str): The text to calculate the reading time for.
        wpm (int, optional): The reading speed in words per minute. Defaults to None.

    Returns:
        float: The estimated reading time in minutes.
    """
    return utils.read_time(text, format='text', wpm=wpm)
