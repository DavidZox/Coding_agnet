import os
import re
from collections import OrderedDict
from typing import List, Optional, NamedTuple

# Define the namedtuple for the index
Index = NamedTuple('Index', [('nationalities', dict), ('cities', dict), ('countries', dict)])

def get_data_path(path: str) -> str:
    """Utility function to construct a file path by joining the root directory with a given path."""
    return os.path.join(os.path.dirname(__file__), 'data_file', path)

def read_table(filename: str, usecols: List[int], sep: str = '\t', comment: str = '#', encoding: str = 'utf-8', skip: int = 0) -> dict:
    """Parses data files to create dictionaries mapping terms to their corresponding values."""
    data = {}
    with open(get_data_path(filename), encoding=encoding) as file:
        for _ in range(skip):
            next(file)
        for line in file:
            if line.startswith(comment):
                continue
            parts = line.strip().split(sep)
            key = parts[usecols[0]]
            value = parts[usecols[1]]
            data[key] = value
    return data

def build_index() -> Index:
    """Loads data from text files and creates an index of nationalities, cities, and countries."""
    nationalities = read_table('nationalities.txt', usecols=[0, 1], skip=1)
    cities = read_table('cities15000.txt', usecols=[1, 8], sep='\t', skip=1)
    countries = read_table('countryInfo.txt', usecols=[4, 0], sep='\t', skip=1)
    return Index(nationalities=nationalities, cities=cities, countries=countries)

class GeoText:
    def __init__(self, text: str, country: Optional[str] = None):
        self.text = text
        self.country = country
        self.countries = []
        self.cities = []
        self.nationalities = []
        self.country_mentions = OrderedDict()
        self.city_regex = re.compile(r'\b(?:' + '|'.join(re.escape(city) for city in build_index().cities.keys()) + r')\b', re.IGNORECASE)
        self._find_candidates(text)
        self._extract_countries(self._find_candidates(text))
        self._extract_cities(self._find_candidates(text), country)
        self._extract_nationalities(self._find_candidates(text))
        self._calculate_country_mentions()

    def _find_candidates(self, text: str) -> List[str]:
        """Finds potential place names in the text."""
        return self.city_regex.findall(text)

    def _extract_countries(self, candidates: List[str]):
        """Extracts country names from the candidates."""
        index = build_index()
        for candidate in candidates:
            if candidate in index.cities.values():
                country_code = index.cities[candidate]
                country_name = index.countries.get(country_code)
                if country_name and country_name not in self.countries:
                    self.countries.append(country_name)

    def _extract_cities(self, candidates: List[str], country: Optional[str]):
        """Extracts city names from the candidates, optionally filtered by country."""
        index = build_index()
        for candidate in candidates:
            if candidate in index.cities and (not country or index.cities[candidate] == country):
                if candidate not in self.cities:
                    self.cities.append(candidate)

    def _extract_nationalities(self, candidates: List[str]):
        """Extracts nationality terms from the candidates."""
        index = build_index()
        for candidate in candidates:
            if candidate.lower() in index.nationalities:
                if candidate not in self.nationalities:
                    self.nationalities.append(candidate)

    def _calculate_country_mentions(self):
        """Counts mentions of countries."""
        index = build_index()
        for city in self.cities:
            country_code = index.cities[city]
            country_name = index.countries.get(country_code)
            if country_name:
                self.country_mentions[country_name] = self.country_mentions.get(country_name, 0) + 1
