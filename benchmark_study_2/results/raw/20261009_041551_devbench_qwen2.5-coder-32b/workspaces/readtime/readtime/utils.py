import re
from bs4 import BeautifulSoup
import markdown2

def read_time(content, format, wpm=265):
    if format == 'text':
        text = content
        images = 0
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
    words = len(re.findall(r'\w+', text))
    seconds = words / wpm * 60
    seconds += images * 12  # Assuming 12 seconds per image
    return seconds

def parse_html(el):
    soup = BeautifulSoup(el, 'html.parser')
    text = soup.get_text()
    images = len(soup.find_all('img'))
    return text, images
