import sys
import os

# Add the current directory to sys.path to ensure 'geotext' can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from geotext import GeoText

def main():
    text = "I am traveling from New York, USA to Paris, France. I love eating French food and meeting French people."
    
    print(f"Input text: {text}")
    print("-" * 20)
    
    # Initialize GeoText
    # We can optionally specify a country code to filter cities
    gt = GeoText(text)
    
    print(f"Countries found: {gt.countries}")
    print(f"Cities found: {gt.cities}")
    print(f"Nationalities found: {gt.nationalities}")
    print(f"Country mentions: {dict(gt.country_mentions)}")
    
    print("-" * 20)
    
    # Example with country filtering
    text2 = "I visited Tokyo, Japan and Seoul, South Korea."
    print(f"Input text 2: {text2}")
    gt2 = GeoText(text2, country='JP')
    print(f"Cities found (filtered by JP): {gt2.cities}")

if __name__ == "__main__":
    main()
