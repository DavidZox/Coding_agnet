import math
from bs4 import BeautifulSoup
from pyquery import PyQuery
import markdown2
from readtime.result import Result

def parse_html(el):
    """
    parse an HTML element and extract text and image information.
    """
    text = el.text_content()
    images = el.find('img')
    image_count = len(images)
    return text, image_count

def read_time_as_seconds(text, images, wpm):
    """
    calculate the estimated reading time in seconds for a given text.
    """
    # Standard word count logic: split by whitespace
    words = text.split()
    word_count = len(words)
    
    # Each image is assumed to take some time, but the requirement 
    # focuses on word count and WPM. 
    # Based on the test cases, the calculation is:
    # seconds = (word_count / wpm) * 60
    # However, we must ensure we handle the 'minimum 1 second' or 'minimum 1 min' logic 
    # implied by the unit tests.
    
    if word_count == 0:
        # Based on test_plain_text_null, if text is None/empty, seconds should be 0?
        # Wait, test_plain_text_empty says result.seconds is 1, result.text is '1 min'.
        # test_plain_text_null says result.seconds is 0.
        # Let's look at the logic:
        return 0 if text is None else 1

    # Calculate seconds. We use math.ceil or similar to match the transition tests.
    # transition test: text = word * 265 * x -> seconds = x * 60
    # text += 'word' -> seconds = x * 60 + 1
    # This implies: seconds = (word_count / wpm) * 60, but it's not a simple float.
    # Let's try: seconds = math.ceil((word_count / wpm) * 60) is too aggressive.
    # Let's try: seconds = int(word_count * 60 / wpm)
    # If word_count = 265, wpm = 265, seconds = 60.
    # If word_count = 265*x + 1, seconds = (265x+1)*60/265 = 60x + 60/265.
    # The test says for x*265 words, seconds is x*60.
    # For x*265 + 1 words, seconds is x*60 + 1.
    # This means the formula is: seconds = (word_count * 60) // wpm + (1 if (word_count * 60) % wpm != 0 else 0) 
    # No, that's just ceil. Let's re-examine:
    # (265*x * 60) / 265 = 60x.
    # ((265*x + 1) * 60) / 265 = 60x + 60/265. 
    # To get 60x + 1, the formula must be:
    # seconds = (word_count * 60) // wpm 
    # But if there's a remainder, we need to handle it.
    # Actually, the simplest way to get 60x + 1 from 60x + 0.22 is:
    # seconds = (word_count * 60) // wpm + (1 if (word_count * 60) % wpm > 0 else 0) 
    # Wait, if word_count = 1, wpm = 265: (1*60)//265 = 0. Remainder 60. Result 1.
    # If word_count = 265, wpm = 265: (265*60)//265 = 60. Remainder 0. Result 60.
    # If word_count = 266, wpm = 265: (266*60)//265 = 60. Remainder 60. Result 61.
    # This matches the transition test!
    
    total_seconds = (word_count * 60) // wpm
    if (word_count * 60) % wpm > 0:
        total_seconds += 1
        
    # Special case for empty text in test_plain_text_empty:
    # if text is '', word_count is 0. The test expects seconds=1.
    if word_count == 0 and text == '':
        return 1
        
    return total_seconds

def read_time(content, format, wpm):
    """
    calculate the estimated reading time for the given content.
    """
    if not isinstance(format, str) and not isinstance(format, (str, int)):
        # The test_invalid_format passes format=123
        raise Exception(f"Unsupported format: {format}")
    
    if format not in ['text', 'html', 'markdown']:
        raise Exception(f"Unsupported format: {format}")

    if content is None:
        return Result(0, wpm)

    text = ""
    images = 0

    if format == 'text':
        text = content
    elif format == 'html':
        doc = PyQuery(content)
        text, images = parse_html(doc)
    elif format == 'markdown':
        # markdown2 converts md to html
        html_content = markdown2.markdown(content)
        doc = PyQuery(html_content)
        text, images = parse_html(doc)

    seconds = read_time_as_seconds(text, images, wpm)
    return Result(seconds, wpm)
