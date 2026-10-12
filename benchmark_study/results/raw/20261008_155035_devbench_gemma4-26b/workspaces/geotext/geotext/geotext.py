import os
import re
from collections import namedtuple, OrderedDict

def get_data_path(path):
    """
    Construct a file path by joining the root directory with a given path.
    """
    # Assuming the script is in geotext/geotext.py, the root is one level up.
    # The data_file is in the same directory as geotext.py.
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # If the path already starts with 'data_file/', it's relative to the package directory
    # which is the same as base_dir.
    return os.path.join(base_dir, path)

def read_table(filename, usecols=None, sep='\t', comment='', encoding='utf-8', skip=0):
    """
    Parses data files to create dictionaries mapping terms to their corresponding values.
    """
    data = {}
    # Check if filename is already an absolute path or relative to current working directory
    # If it's just a filename like 'data_file/xxx', we use get_data_path
    if not os.path.isabs(filename) and not filename.startswith('./') and not filename.startswith('../'):
        path = get_data_path(filename)
    else:
        path = filename
    
    if not os.path.exists(path):
        return data

    with open(path, 'r', encoding=encoding) as f:
        lines = f.readlines()[skip:]
        for line in lines:
            line = line.strip()
            if not line or line.startswith(comment):
                continue
            
            parts = line.split(sep)
            
            # If usecols is provided, we only care about those indices
            if usecols is not None and len(usecols) >= 2:
                # We implement a flexible version where the first requested col is key
                # and the second is value.
                idx_key = usecols[0]
                idx_val = usecols[1]
                
                if idx_key < len(parts) and idx_val < len(parts):
                    key = parts[idx_key]
                    val = parts[idx_val]
                    if key:
                        data[key] = val
            else:
                pass
    return data

def build_index():
    """
    Loads data from text files and creates an index of nationalities, cities, and countries.
    Returns a namedtuple.
    """
    # 1. Load Nationalities
    # Format: afghan:AF
    nationalities_dict = {}
    # We use the relative path from the package root
    nat_path = get_data_path('data_file/nationalities.txt')
    if os.path.exists(nat_path):
        with open(nat_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and ':' in line:
                    nat, code = line.split(':')
                    nationalities_dict[nat.lower()] = code

    # 2. Load Countries
    # Format: AD (0) ... Andorra (4) ...
    # We need a mapping of Country Name -> ISO Code and ISO Code -> Country Name
    countries_name_to_code = {}
    countries_code_to_name = {}
    # read_table handles get_data_path internally
    # countryInfo.txt: AD (0) AND (1) 020 (2) AN (3) Andorra (4) ...
    country_info = read_table('data_file/countryInfo.txt', usecols=[0, 4])
    for code, name in country_info.items():
        if name:
            countries_name_to_code[name] = code
            countries_code_to_name[code] = name

    # 3. Load Cities
    # Format: ID (0), Name (1), ... Country Code (13)
    # We need a mapping of City Name -> Country Code
    cities_dict = {}
    cities_path = get_data_path('data_file/cities15000.txt')
    if os.path.exists(cities_path):
        with open(cities_path, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) > 13:
                    city_name = parts[1]
                    country_code = parts[13]
                    cities_dict[city_name] = country_code

    # 4. Load City Patches
    # Format: oklahoma (0) US (1)
    patches = read_table('data_file/citypatches.txt', usecols=[0, 1])
    for city, code in patches.items():
        cities_dict[city] = code

    Index = namedtuple('Index', ['nationalities', 'cities', 'countries'])
    return Index(
        nationalities=nationalities_dict,
        cities=cities_dict,
        countries=countries_code_to_name # Using code to name for easier lookup
    )

class GeoText:
    def __init__(self, text, country=None):
        self.text = text
        self.country = country
        self.countries = []
        self.cities = []
        self.nationalities = []
        self.country_mentions = OrderedDict()
        
        self._index = build_index()
        self._city_regex = re.compile(r'\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b')
        
        candidates = self._find_candidates(text)
        self._extract_countries(candidates)
        self._extract_cities(candidates, country)
        self._extract_nationalities(candidates)
        self._calculate_country_mentions()

    def _find_candidates(self, text):
        # Find potential proper nouns (capitalized words)
        return self._city_regex.findall(text)

    def _extract_countries(self, candidates):
        # Check if candidates are in the countries index (by name)
        # The index.countries is code -> name. We need name -> code for lookup.
        name_to_code = {name: code for code, name in self._index.countries.items()}
        
        found_countries = []
        for cand in candidates:
            if cand in name_to_code:
                found_countries.append(cand)
        
        # Remove duplicates while preserving order
        self.countries = list(OrderedDict.fromkeys(found_countries))

    def _extract_cities(self, candidates, country_filter):
        found_cities = []
        for cand in candidates:
            if cand in self._index.cities:
                city_code = self._index.cities[cand]
                # If country filter is provided, check if city belongs to that country
                if country_filter:
                    # Convert country name to code
                    filter_code = None
                    for code, name in self._index.countries.items():
                        if name == country_filter:
                            filter_code = code
                            break
                    if filter_code and city_code != filter_code:
                        continue
                found_cities.append(cand)
        
        self.cities = list(OrderedDict.fromkeys(found_cities))

    def _extract_nationalities(self, candidates):
        found_nationalities = []
        for cand in candidates:
            if cand.lower() in self._index.nationalities:
                found_nationalities.append(cand)
        
        self.nationalities = list(OrderedDict.fromkeys(found_nationalities))

    def _calculate_country_mentions(self):
        # Count how many times each country name appears in the text
        # We use the countries list to find matches
        # We need to scan the text for country names
        # To avoid partial matches, we use word boundaries
        for code, name in self._index.countries.items():
            # We need to find how many times 'name' appears in self.text
            # Using regex to ensure whole word match
            pattern = r'\b' + re.escape(name) + r'\b'
            matches = re.findall(pattern, self.text)
            if matches:
                self.country_mentions[name] = len(matches)
