#! /usr/bin/env python
# -*- coding: utf-8 -*-

from geotext import GeoText

def main():
    text = "I love New York and Paris. I also visited Tokyo and Berlin. The people in Osaka and Kyoto are very friendly."
    geo = GeoText(text)

    print("Countries found:", geo.countries)
    print("Cities found:", geo.cities)
    print("Nationalities found:", geo.nationalities)
    print("Country mentions:", geo.country_mentions)

if __name__ == "__main__":
    main()
