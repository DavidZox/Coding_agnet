import os
import re
from collections import namedtuple, OrderedDict

# Define the namedtuple for the index
Index = namedtuple('Index', ['nationalities', 'cities', 'countries'])

def get_data_path(path):
    """
    Constructs a file path by joining the root directory with a given path.
    """
    # Assuming the script is in geotext/geotext.py, 
    # the data_file is in the same directory.
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, path)

def read_table(filename, usecols=None, sep='\t', comment='', encoding='utf-8', skip=0):
    """
    Parses data files to create dictionaries mapping terms to their corresponding values.
    """
    data = {}
    full_path = get_data_path(filename)
    
    if not os.path.exists(full_path):
        return data

    with open(full_path, 'r', encoding=encoding) as f:
        lines = f.readlines()[skip:]
        for line in lines:
            line = line.strip()
            if not line or line.startswith(comment):
                continue
            
            parts = line.split(sep)
            
            # If usecols is provided, we only care about those indices
            if usecols is not None:
                # Create a subset of parts based on usecols
                row = []
                for col in usecols:
                    if col < len(parts):
                        row.append(parts[col])
                    else:
                        row.append(None)
                
                # For the purpose of this library, we assume the first column 
                # is the key and the second is the value if usecols=[0, 1]
                if len(row) >= 2 and row[0] and row[1]:
                    data[row[0]] = row[1]
            else:
                # Default behavior: if no usecols, we can't reliably map.
                # But based on the requirements, we expect specific formats.
                pass
    return data

def build_index():
    """
    Loads data from text files and creates an index.
    """
    # 1. Load Nationalities
    # Format: afghan:AF
    nationalities = {}
    nat_path = get_data_path('data_file/nationalities.txt')
    if os.path.exists(nat_path):
        with open(nat_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and ':' in line:
                    term, code = line.split(':', 1)
                    nationalities[term.lower()] = code

    # 2. Load Countries
    # Format: AD AND 020 AN Andorra ...
    # We need a mapping of Country Name -> ISO Code and ISO Code -> Country Name
    countries_map = {} # Name -> Code
    countries_code_to_name = {} # Code -> Name
    country_info_path = get_data_path('data_file/countryInfo.txt')
    if os.path.exists(country_info_path):
        with open(country_info_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split('\t')
                if len(parts) >= 5:
                    iso_code = parts[0]
                    country_name = parts[4]
                    countries_map[country_name] = iso_code
                    countries_code_to_name[iso_code] = country_name

    # 3. Load Cities
    # Format: geonameid \t city_name \t ... \t country_code
    # cities15000.txt: 2081986 Palikir ... FM
    # We need a way to map city name -> country code
    cities = {} # city_name -> country_code
    cities_path = get_data_path('data_file/cities15000.txt')
    if os.path.exists(cities_path):
        with open(cities_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split('\t')
                if len(parts) >= 11:
                    # Based on the example: 
                    # parts[1] is city name, parts[10] is country code
                    city_name = parts[1]
                    country_code = parts[10]
                    cities[city_name.lower()] = country_code

    # 4. Load City Patches
    # Format: oklahoma US
    city_patches = {}
    patches_path = get_data_path('data_file/citypatches.txt')
    if os.path.exists(patches_path):
        with open(patches_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        city_patches[parts[0].lower()] = parts[1]

    # Merge patches into cities
    for patch_city, country_code in city_patches.items():
        cities[patch_city] = country_code

    return Index(nationalities=nationalities, cities=cities, countries=countries_map)

class GeoText:
    def __init__(self, text, country=None):
        self.text = text
        self.country = country
        self.countries = []
        self.cities = []
        self.nationalities = []
        self.country_mentions = OrderedDict()
        
        # This would be initialized by the build_index and used in extraction
        # For now, we just define the structure as per UML
        self._index = build_index()
        self._city_regex = re.compile(r'\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b')
        
        candidates = self._find_candidates()
        self.countries = self._extract_countries(candidates)
        self.cities = self._extract_cities(candidates, self.country)
        self.nationalities = self._extract_nationalities(candidates)
        self._calculate_country_mentions()

    def _find_candidates(self):
        return self._city_regex.findall(self.text)

    def _extract_countries(self, candidates):
        found_countries = []
        for candidate in candidates:
            if candidate in self._index.countries:
                found_countries.append(candidate)
        return found_countries

    def _extract_cities(self, candidates, country):
        found_cities = []
        for candidate in candidates:
            candidate_lower = candidate.lower()
            if candidate_lower in self._index.cities:
                city_country_code = self._index.cities[candidate_lower]
                if country is None or city_country_code == country:
                    found_cities.append(candidate)
        return found_cities

    def _extract_nationalities(self, candidates):
        found_nationalities = []
        for candidate in candidates:
            if candidate.lower() in self._index.nationalities:
                found_nationalities.append(candidate)
        return found_nationalities

    def _calculate_country_mentions(self):
        for country in self.countries:
            if country in self.country_mentions:
                self.country_mentions[country] += 1
            else:
                self.country_mentions[country] = 1
