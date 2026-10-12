import markdown2
from bs4 import BeautifulSoup
from pyquery import PyQuery as pq

def read_time(content, format, wpm=265):
    if format == 'text':
        words = len(content.split())
    elif format == 'html':
        text, images = parse_html(content)
        words = len(text.split())
    elif format == 'markdown':
        html = markdown2.markdown(content)
        text, images = parse_html(html)
        words = len(text.split())
    else:
        raise ValueError("Unsupported format")
    
    seconds = read_time_as_seconds(words, images, wpm)
    return Result(seconds, wpm)

def read_time_as_seconds(words, images, wpm):
    seconds = (words / wpm) * 60
    # Assuming each image adds an additional 12 seconds to reading time
    seconds += images * 12
    return seconds

def parse_html(el):
    soup = BeautifulSoup(el, 'html.parser')
    pq_el = pq(soup)
    text = pq_el.text()
    images = len(pq_el('img'))
    return text, images
