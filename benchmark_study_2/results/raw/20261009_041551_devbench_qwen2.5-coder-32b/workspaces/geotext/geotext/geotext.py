import os
import csv
from collections import defaultdict, namedtuple, OrderedDict
import re

def get_data_path(path):
    root_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(root_dir, 'data_file', path)

def read_table(filename, usecols, sep, comment, encoding, skip):
    data_path = get_data_path(filename)
    data_dict = defaultdict(list)
    
    with open(data_path, 'r', encoding=encoding) as file:
        reader = csv.reader(file, delimiter=sep, comment=comment)
        for _ in range(skip):
            next(reader)
        for row in reader:
            key = row[usecols[0]]
            value = row[usecols[1]]
            data_dict[key].append(value)
    
    return data_dict

def build_index():
    Index = namedtuple('Index', ['nationalities', 'cities', 'countries'])
    
    nationalities = read_table('nationalities.txt', usecols=[0, 1], sep=':', comment='#', encoding='utf-8', skip=0)
    cities = read_table('cities15000.txt', usecols=[1, 8], sep='\t', comment='#', encoding='utf-8', skip=1)
    countries = read_table('countryInfo.txt', usecols=[4, 0], sep='\t', comment='#', encoding='utf-8', skip=1)
    
    return Index(nationalities=nationalities, cities=cities, countries=countries)

class GeoText:
    def __init__(self, text, country=None):
        self.text = text
        self.country = country
        self.countries = []
        self.cities = []
        self.nationalities = []
        self.country_mentions = OrderedDict()
        self.city_regex = re.compile(r'\b(?:' + '|'.join(build_index().cities.keys()) + r')\b', re.IGNORECASE)
        
        candidates = self._find_candidates(text)
        self._extract_countries(candidates)
        self._extract_cities(candidates, country)
        self._extract_nationalities(candidates)
        self._calculate_country_mentions()

    def _find_candidates(self, text):
        # Create a regex pattern to match potential city names
        city_names = build_index().cities.keys()
        city_pattern = r'\b(?:' + '|'.join(re.escape(city) for city in city_names) + r')\b'
        city_regex = re.compile(city_pattern, re.IGNORECASE)
        return city_regex.findall(text)

    def _extract_countries(self, candidates):
        index = build_index()
        for candidate in candidates:
            for country_name, country_codes in index.countries.items():
                if candidate in country_codes:
                    if country_name not in self.countries:
                        self.countries.append(country_name)

    def _extract_cities(self, candidates, country):
        index = build_index()
        for candidate in candidates:
            for city, country_codes in index.cities.items():
                if candidate.lower() == city.lower() and (not country or country in country_codes):
                    if candidate not in self.cities:
                        self.cities.append(candidate)

    def _extract_nationalities(self, candidates):
        index = build_index()
        for candidate in candidates:
            for nationality, country_codes in index.nationalities.items():
                if candidate.lower() == nationality:
                    if nationality not in self.nationalities:
                        self.nationalities.append(nationality)

    def _calculate_country_mentions(self):
        index = build_index()
        for city in self.cities:
            for country_code in index.cities[city]:
                country_name = index.countries.get(country_code, [None])[0]
                if country_name:
                    self.country_mentions[country_name] = self.country_mentions.get(country_name, 0) + 1
