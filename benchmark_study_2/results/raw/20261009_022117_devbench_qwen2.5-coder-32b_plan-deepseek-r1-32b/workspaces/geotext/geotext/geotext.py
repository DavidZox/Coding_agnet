import os
import pandas as pd
from collections import namedtuple, OrderedDict
import re
import argparse

def get_data_path(path):
    """Utility function to construct a file path by joining the root directory with a given path."""
    root_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(root_dir, path)

def read_table(filename, usecols, sep, comment, encoding, skip):
    """Parses data files from the data_file directory to create dictionaries mapping terms to their corresponding values."""
    file_path = get_data_path(os.path.join('data_file', filename))
    data = pd.read_csv(file_path, usecols=usecols, sep=sep, comment=comment, encoding=encoding, skiprows=skip, header=None, dtype=str)
    return data.to_dict(orient='records')

def build_index():
    """Loads data from text files in the data_file directory and creates an index of nationalities, cities, and countries."""
    Index = namedtuple('Index', ['cities', 'countries', 'nationalities'])
    
    # Read cities data
    cities_data = read_table('cities15000.txt', usecols=[1, 8], sep='\t', comment='#', encoding='utf-8', skip=1)
    cities_index = {city[1].lower(): city[8] for city in cities_data}
    
    # Read countries data
    countries_data = read_table('countryInfo.txt', usecols=[0, 4], sep='\t', comment='#', encoding='utf-8', skip=0)
    countries_index = {country[0].lower(): country[4].lower() for country in countries_data}
    
    # Read nationalities data
    nationalities_data = read_table('nationalities.txt', usecols=[0, 1], sep=':', comment=None, encoding='utf-8', skip=0)
    nationalities_index = {nationality[0].lower(): nationality[1].lower() for nationality in nationalities_data}
    
    return Index(cities=cities_index, countries=countries_index, nationalities=nationalities_index)

class GeoText:
    def __init__(self, text, country=None):
        self.text = text
        self.country = country
        self.countries = []
        self.cities = []
        self.nationalities = []
        self.country_mentions = OrderedDict()
        
        self.index = build_index()
        self.city_regex = self._build_city_regex()
        
        self._find_candidates(text)
        self._extract_countries(self.candidates)
        self._extract_cities(self.candidates, country)
        self._extract_nationalities(self.candidates)
        self._calculate_country_mentions()
    
    def _build_city_regex(self):
        city_names = list(self.index.cities.keys())
        city_names.sort(key=len, reverse=True)  # Sort by length to avoid partial matches
        pattern = r'\b(?:' + '|'.join(re.escape(name) for name in city_names) + r')\b'
        return re.compile(pattern, re.IGNORECASE)
    
    def _find_candidates(self, text):
        self.candidates = self.city_regex.findall(text)
    
    def _extract_countries(self, candidates):
        for candidate in candidates:
            country_code = self.index.cities.get(candidate.lower())
            if country_code:
                country_name = self.index.countries.get(country_code.lower())
                if country_name and country_name not in self.countries:
                    self.countries.append(country_name)
    
    def _extract_cities(self, candidates, country):
        for candidate in candidates:
            country_code = self.index.cities.get(candidate.lower())
            if country_code:
                if not country or country_code.lower() == country.lower():
                    if candidate not in self.cities:
                        self.cities.append(candidate)
    
    def _extract_nationalities(self, candidates):
        for candidate in candidates:
            nationality = self.index.nationalities.get(candidate.lower())
            if nationality and nationality not in self.nationalities:
                self.nationalities.append(nationality)
    
    def _calculate_country_mentions(self):
        for city in self.cities:
            country_code = self.index.cities.get(city.lower())
            if country_code:
                country_name = self.index.countries.get(country_code.lower())
                if country_name:
                    if country_name in self.country_mentions:
                        self.country_mentions[country_name] += 1
                    else:
                        self.country_mentions[country_name] = 1

def main():
    parser = argparse.ArgumentParser(description='Extract city and country mentions from text.')
    parser.add_argument('text', type=str, help='The text to analyze.')
    parser.add_argument('--country', type=str, help='Filter cities by country code.', default=None)
    args = parser.parse_args()
    
    geo_text = GeoText(args.text, args.country)
    print(f"Countries: {geo_text.countries}")
    print(f"Cities: {geo_text.cities}")
    print(f"Nationalities: {geo_text.nationalities}")
    print(f"Country Mentions: {geo_text.country_mentions}")

if __name__ == "__main__":
    main()
