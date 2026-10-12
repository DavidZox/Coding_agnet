import markdown2
from bs4 import BeautifulSoup
from pyquery import PyQuery as pq

def read_time(content, format, wpm=265):
    if format == 'text':
        text = content
    elif format == 'html':
        text, images = parse_html(content)
    elif format == 'markdown':
        html = markdown2.markdown(content)
        text, images = parse_html(html)
    else:
        raise ValueError("Unsupported format")
    
    seconds = read_time_as_seconds(text, images, wpm)
    return seconds

def read_time_as_seconds(text, images, wpm=265):
    words = len(text.split())
    seconds = words / wpm * 60
    seconds += images * 12  # Assuming 12 seconds per image
    return seconds

def parse_html(el):
    soup = BeautifulSoup(el, 'lxml')
    pq_el = pq(soup)
    text = pq_el.text()
    images = len(pq_el('img'))
    return text, images
