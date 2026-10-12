import os
import re
from collections import namedtuple, OrderedDict

# Define the namedtuple for the index
Index = namedtuple('Index', ['nationalities', 'cities', 'countries'])

def get_data_path(path):
    """
    Construct a file path by joining the root directory with a given path.
    """
    # Assuming the root directory is the parent of the 'geotext' package
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, 'geotext', path)

def read_table(filename, usecols=None, sep='\t', comment='', encoding='utf-8', skip=0):
    """
    Parses data files to create dictionaries mapping terms to their corresponding values.
    """
    data_dict = {}
    full_path = get_data_path(filename)
    
    if not os.path.exists(full_path):
        return data_dict

    with open(full_path, 'r', encoding=encoding) as f:
        lines = f.readlines()[skip:]
        for line in lines:
            line = line.strip()
            if not line or line.startswith(comment):
                continue
            
            parts = line.split(sep)
            
            # If usecols is provided, we only care about those indices
            # For simplicity in this implementation, we assume usecols is a list of indices
            # and we map the first specified column as key and others as values or specific logic
            if usecols is not None:
                # Extract only the requested columns
                selected_parts = [parts[i] for i in usecols if i < len(parts)]
                if len(selected_parts) >= 1:
                    key = selected_parts[0]
                    # If there's only one column requested, value is the key itself or empty
                    # Based on typical usage, we map key -> value (the rest of the columns)
                    if len(selected_parts) > 1:
                        data_dict[key] = selected_parts[1:]
                    else:
                        data_dict[key] = selected_parts[0]
            else:
                # Default behavior: first column is key, second is value
                if len(parts) >= 2:
                    data_dict[parts[0]] = parts[1]
                elif len(parts) == 1:
                    data_dict[parts[0]] = parts[0]
                    
    return data_dict

def build_index():
    """
    Loads data from text files and creates an index of nationalities, cities, and countries.
    """
    # 1. Load Nationalities
    # Format: afghan:AF
    nationalities_raw = read_table('data_file/nationalities.txt', sep=':')
    # We want a mapping where the nationality name is the key
    nationalities = dict(nationalities_raw)

    # 2. Load Countries
    # Format: ISO (col 0), ..., Country (col 4)
    # Based on countryInfo.txt example: AD (0), AND (1), ..., Andorra (4)
    # We need a way to map Country Name -> ISO Code
    countries = {}
    # Re-reading specifically for country mapping
    full_path = get_data_path('data_file/countryInfo.txt')
    if os.path.exists(full_path):
        with open(full_path, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) > 4:
                    iso = parts[0]
                    country_name = parts[4]
                    countries[country_name] = iso

    # 3. Load Cities
    # Format: cities15000.txt -> population, name, etc.
    # Example: 2081986 (0), Palikir (1), ..., FM (country code)
    # We need to map City Name -> Country Code
    cities = {}
    full_path_cities = get_data_path('data_file/cities15000.txt')
    if os.path.exists(full_path_cities):
        with open(full_path_cities, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) > 10:
                    city_name = parts[1]
                    country_code = parts[10]
                    cities[city_name] = country_code

    return Index(nationalities=nationalities, cities=cities, countries=countries)

class GeoText:
    def __init__(self, text, country=None):
        self.text = text
        self.country = country
        self.countries = []
        self.cities = []
        self.nationalities = []
        self.country_mentions = OrderedDict()
        self.city_regex = re.compile(r'\b\w+\b')
        
        self._index = build_index()
        
        candidates = self._find_candidates(text)
        self.countries = self._extract_countries(candidates)
        self.cities = self._extract_cities(candidates, country)
        self.nationalities = self._extract_nationalities(candidates)
        self._calculate_country_mentions()

    def _find_candidates(self, text):
        return self.city_regex.findall(text)

    def _extract_countries(self, candidates):
        found_countries = []
        # The index.countries maps Country Name -> ISO
        # We need to check if candidates match country names
        for candidate in candidates:
            if candidate in self._index.countries:
                found_countries.append(candidate)
        return found_countries

    def _extract_cities(self, candidates, country):
        found_cities = []
        # The index.cities maps City Name -> Country Code
        # We need to check if candidates match city names
        for candidate in candidates:
            if candidate in self._index.cities:
                city_country_code = self._index.cities[candidate]
                # If country is specified, filter by it
                if country:
                    # Check if the city's country code matches the provided country's ISO
                    # We need to find the ISO for the provided country name
                    target_iso = self._index.countries.get(country)
                    if target_iso and city_country_code == target_iso:
                        found_cities.append(candidate)
                else:
                    found_cities.append(candidate)
        return found_cities

    def _extract_nationalities(self, candidates):
        found_nationalities = []
        # The index.nationalities maps Nationality -> ISO
        for candidate in candidates:
            if candidate in self._index.nationalities:
                found_nationalities.append(candidate)
        return found_nationalities

    def _calculate_country_mentions(self):
        # Count mentions of countries found in the text
        # We use the country names found in self.countries
        for country in self.countries:
            self.country_mentions[country] = self.country_mentions.get(country, 0) + 1
