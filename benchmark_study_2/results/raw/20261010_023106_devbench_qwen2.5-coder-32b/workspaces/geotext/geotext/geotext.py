import os
import csv
from collections import defaultdict, namedtuple, OrderedDict
import re

def get_data_path(path):
    """Construct a file path by joining the root directory with a given path."""
    root_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(root_dir, 'data_file', path)

def read_table(filename, usecols, sep, comment, encoding, skip):
    """Parses data files from the data_file directory to create dictionaries mapping terms to their corresponding values based on the specified columns."""
    file_path = get_data_path(filename)
    data = defaultdict(list)
    
    with open(file_path, 'r', encoding=encoding) as file:
        reader = csv.reader(file, delimiter=sep, comment=comment)
        for _ in range(skip):
            next(reader)
        for row in reader:
            for col in usecols:
                if col < len(row):
                    key = row[col]
                    data[key].extend(row)
    
    return data

def build_index():
    """Loads data from text files in the data_file directory and creates an index of nationalities, cities, and countries in the form of a namedtuple."""
    Index = namedtuple('Index', ['nationalities', 'cities', 'countries'])
    
    nationalities = read_table('nationalities.txt', usecols=[0], sep=':', comment='#', encoding='utf-8', skip=0)
    cities = read_table('cities15000.txt', usecols=[1], sep='\t', comment='#', encoding='utf-8', skip=1)
    countries = read_table('countryInfo.txt', usecols=[4], sep='\t', comment='#', encoding='utf-8', skip=1)
    
    return Index(nationalities=nationalities, cities=cities, countries=countries)

class GeoText:
    def __init__(self, text, country=None):
        self.text = text
        self.country = country
        self.countries = []
        self.cities = []
        self.nationalities = []
        self.country_mentions = OrderedDict()
        self.index = build_index()
        self.city_regex = re.compile(r'\b(?:' + '|'.join(self.index.cities.keys()) + r')\b', re.IGNORECASE)
        self._find_candidates()
        self._extract_countries()
        self._extract_cities()
        self._extract_nationalities()
        self._calculate_country_mentions()

    def _find_candidates(self):
        self.candidates = self.city_regex.findall(self.text)

    def _extract_countries(self):
        self.countries = [candidate for candidate in self.candidates if candidate.lower() in (name.lower() for name in self.index.countries.keys())]

    def _extract_cities(self):
        self.cities = [candidate for candidate in self.candidates if candidate.lower() in (name.lower() for name in self.index.cities.keys())]

    def _extract_nationalities(self):
        self.nationalities = [candidate for candidate in self.candidates if candidate.lower() in (name.lower() for name in self.index.nationalities.keys())]

    def _calculate_country_mentions(self):
        for country in self.countries:
            self.country_mentions[country] = self.country_mentions.get(country, 0) + 1
