from geotext import GeoText

def main():
    # Sample text containing various locations and nationalities
    text = (
        "I traveled from New York, USA to Tokyo, Japan last year. "
        "I met some French people and an Italian traveler in Paris. "
        "The weather in London is quite unpredictable, unlike in Madrid. "
        "I love eating Chinese food while sitting in a cafe in Berlin."
    )

    # Initialize GeoText
    # We can optionally provide a country code to filter cities
    geotext = GeoText(text)

    # Display extracted information
    print("--- Original Text ---")
    print(text)
    print("\n--- Extracted Information ---")
    
    print(f"Countries: {geotext.countries}")
    print(f"Cities: {geotext.cities}")
    print(f"Nationalities: {geotext.nationalities}")
    
    print("\n--- Country Mentions ---")
    for country, count in geotext.country_mentions.items():
        print(f"{country}: {count}")

    # Example with country filtering
    print("\n--- Filtering Cities by Country (US) ---")
    geotext_us = GeoText(text, country='US')
    print(f"Cities in US: {geotext_us.cities}")

if __name__ == "__main__":
    main()
