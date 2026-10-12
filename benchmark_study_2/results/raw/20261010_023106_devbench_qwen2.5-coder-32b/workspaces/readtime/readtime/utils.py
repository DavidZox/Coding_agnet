import markdown2
from bs4 import BeautifulSoup
from pyquery import PyQuery as pq

def read_time(content, format, wpm=265):
    if format == 'text':
        text = content
        images = 0
    elif format == 'html':
        parsed_content = parse_html(content)
        text = parsed_content['text']
        images = parsed_content['images']
    elif format == 'markdown':
        html = markdown2.markdown(content)
        parsed_content = parse_html(html)
        text = parsed_content['text']
        images = parsed_content['images']
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
    soup = BeautifulSoup(el, 'html.parser')
    # Convert BeautifulSoup object to string before passing to pyquery
    pq_content = pq(str(soup))
    text = pq_content.text()
    images = len(pq_content('img'))
    return {'text': text, 'images': images}
