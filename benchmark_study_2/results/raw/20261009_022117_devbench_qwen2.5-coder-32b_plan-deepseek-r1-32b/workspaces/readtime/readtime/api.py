from .utils import read_time

def of_text(text, wpm=265):
    return read_time(text, 'text', wpm)

def of_html(html, wpm=265):
    return read_time(html, 'html', wpm)

def of_markdown(markdown, wpm=265):
    return read_time(markdown, 'markdown', wpm)
