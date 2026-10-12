from .utils import read_time
from .result import Result

def of_text(text, wpm=265):
    seconds = read_time(text, 'text', wpm)
    return Result(seconds, wpm)

def of_html(html, wpm=265):
    seconds = read_time(html, 'html', wpm)
    return Result(seconds, wpm)

def of_markdown(markdown, wpm=265):
    seconds = read_time(markdown, 'markdown', wpm)
    return Result(seconds, wpm)
