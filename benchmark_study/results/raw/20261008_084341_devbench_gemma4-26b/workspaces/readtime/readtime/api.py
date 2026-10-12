from readtime.utils import read_time

def of_text(text, wpm=265):
    """
    Calculate the reading time of a given text.
    """
    return read_time(text, 'text', wpm)

def of_html(html, wpm=265):
    """
    Calculate the reading time of an HTML document.
    """
    return read_time(html, 'html', wpm)

def of_markdown(markdown, wpm=265):
    """
    Calculate the reading time of a markdown text.
    """
    return read_time(markdown, 'markdown', wpm)
