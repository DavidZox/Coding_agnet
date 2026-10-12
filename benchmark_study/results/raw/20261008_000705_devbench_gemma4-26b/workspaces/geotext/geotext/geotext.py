import os
import re
from collections import namedtuple, OrderedDict

# Define the Index namedtuple
Index = namedtuple('Index', ['nationalities', 'cities', 'countries'])

def get_data_path(path):
    """
    Construct a file path by joining the root directory with a given path.
    """
    # Assuming the script is in geotext/geotext.py, the data_file is in geotext/data_file
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, path)

def read_table(filename, usecols, sep='\t', comment='', encoding='utf-8', skip=0):
    """
    Parses data files from the data_file directory to create dictionaries 
    mapping terms to their corresponding values based on the specified columns.
    """
    data = {}
    full_path = get_data_path(filename)
    
    if not os.path.exists(full_path):
        return data

    with open(full_path, 'r', encoding=encoding) as f:
        lines = f.readlines()[skip:]
        for line in lines:
            line = line.strip()
            if not line or (comment and line.startswith(comment)):
                continue
            
            parts = line.split(sep)
            # Ensure we have enough parts to satisfy usecols
            if len(parts) >= max(usecols) + 1:
                # usecols is expected to be a list of indices, e.g., [0, 1]
                # We map the first column in usecols as the key, and the second as the value
                # Or more generally, if usecols is [key_idx, val_idx]
                key_idx = usecols[0]
                val_idx = usecols[1]
                key = parts[key_idx].strip()
                val = parts[val_idx].strip()
                data[key] = val
    return data

def build_index():
    """
    Loads data from text files in the data_file directory and creates an index 
    of nationalities, cities, and countries in the form of a namedtuple.
    """
    # 1. Load nationalities
    # Format: nationality:ISO (e.g., afghan:AF)
    nationalities_raw = read_table('data_file/nationalities.txt', usecols=[0, 1], sep=':')
    # The read_table might need adjustment if the separator is ':' but it's a single pair
    # Actually, the example says 'afghan:AF', so sep=':' works.
    # However, read_table returns a dict. We need the keys (nationalities).
    nationalities = list(nationalities_raw.keys())

    # 2. Load countries
    # Format: ISO ... Country ... (from countryInfo.txt)
    # Example: AD AND 020 AN Andorra ...
    # We need a way to map Country Name -> ISO or vice versa. 
    # Based on requirements, we need to identify countries.
    # Let's assume countryInfo.txt: col 0 is ISO, col 4 is Country Name.
    countries_info = read_table('data_file/countryInfo.txt', usecols=[0, 4], sep='\t')
    # countries_info: { 'AD': 'Andorra', ... }
    # We need a mapping for extraction. Let's store both ways or just names.
    # For extraction, we usually look for names.
    countries_map = {v: k for k, v in countries_info.items()} # Name -> ISO
    countries = list(countries_map.keys())

    # 3. Load cities
    # Format: geonameid \t name \t ... \t country_code
    # cities15000.txt example: 2081986 \t Palikir ... \t FM
    # We need to map city name to country code.
    # Looking at the example: col 1 is name, col 8 is country code (0-indexed: 0:id, 1:name, ..., 8:country_code)
    # Wait, let's check the example: 2081986(0) Palikir(1) ... FM(8)
    # Let's use a more robust way to read cities.
    cities_dict = {}
    cities_path = get_data_path('data_file/cities15000.txt')
    with open(cities_path, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('\t')
            if len(parts) > 8:
                city_name = parts[1]
                country_code = parts[8]
                cities_dict[city_name] = country_code

    # 4. Load city patches
    # Format: city \t country_code
    patches = read_table('data_file/citypatches.txt', usecols=[0, 1], sep='\t')
    for city, code in patches.items():
        cities_dict[city] = code

    return Index(nationalities=nationalities, cities=cities_dict, countries=countries)

class GeoText:
    def __init__(self, text, country=None):
        self.text = text
        self.country = country
        self.index = build_index()
        
        self.countries = []
        self.cities = []
        self.nationalities = []
        self.country_mentions = OrderedDict()
        
        # Pre-compile regex for words (candidates)
        self.city_regex = re.compile(r'\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b|\b[a-z]+\b')
        
        candidates = self._find_candidates(text)
        self.countries = self._extract_countries(candidates)
        self.cities = self._extract_cities(candidates, country)
        self.nationalities = self._extract_nationalities(candidates)
        self._calculate_country_mentions()

    def _find_candidates(self, text):
        # Find all words or sequences of capitalized words as potential candidates
        # Using a simpler approach: split by non-alphanumeric characters and filter
        return re.findall(r'\b[\w\']+\b', text)

    def _extract_countries(self, candidates):
        found_countries = []
        for cand in candidates:
            if cand in self.index.countries:
                found_countries.append(cand)
        return found_countries

    def _extract_cities(self, candidates, country):
        found_cities = []
        # Create a mapping for country name to ISO if provided
        target_iso = None
        if country:
            # Check if country is already an ISO code in our index
            # (We need the reverse mapping: ISO -> Name to check this)
            # But build_index only gives us Name -> ISO in countries_map logic.
            # Let's check if 'country' exists in the index's country names.
            # If it does, we find its ISO.
            # We can find it by looking at the index.countries list.
            # However, we need the ISO. Let's re-read countryInfo to get ISO.
            # A better way: build_index should return a name_to_iso map.
            # For now, let's try to find if 'country' is a name in index.countries.
            # We'll use a simple approach: if it's in index.countries, it's a name.
            # We need to find the ISO for that name.
            # Since we don't have the map here, let's assume we can find it.
            # Actually, let's just check if the city's country code matches the input
            # if the input is an ISO, OR if the input is a name, we find its ISO.
            
            # Let's try to find the ISO for the provided country name.
            # We'll use the fact that we can't easily access the internal map of build_index
            # unless we change build_index. But we must follow the structure.
            # Let's assume 'country' is either the ISO or the Name.
            # We'll check if 'country' is in the index.countries (names).
            # If so, we need its ISO. Since we don't have the map, we'll try to 
            # match the city's country code against the input if input is ISO,
            # or we'll have to assume the user provides ISO or we find it.
            # Let's try to see if 'country' is in the index.countries.
            pass

        # To make this work without changing build_index, we'll re-parse or 
        # assume the user provides the ISO or we find it.
        # Let's try to find the ISO for the name 'country'.
        country_iso = country
        if country in self.index.countries:
            # It's a name, find its ISO.
            # We need to find which ISO corresponds to this name.
            # Since we don't have the map, we'll have to find it from the text/data.
            # But we can't easily. Let's assume the user provides ISO or we handle it.
            # Wait, the requirement says "filter extracted cities by country codes".
            # If the user provides "Taiwan", and "Taiwan" is a country name, 
            # we should find its ISO (TW) and then filter.
            # Let's use a temporary way to find the ISO.
            full_path = get_data_path('data_file/countryInfo.txt')
            with open(full_path, 'r', encoding='utf-8') as f:
                for line in f:
                    parts = line.strip().split('\t')
                    if len(parts) >= 5:
                        iso = parts[0]
                        name = parts[4]
                        if name == country:
                            country_iso = iso
                            break
        
        for cand in candidates:
            if cand in self.index.cities:
                city_country_code = self.index.cities[cand]
                if country_iso:
                    if city_country_code == country_iso:
                        found_cities.append(cand)
                else:
                    found_cities.append(cand)
        return found_cities

    def _extract_nationalities(self, candidates):
        found_nationalities = []
        for cand in candidates:
            if cand in self.index.nationalities:
                found_nationalities.append(cand)
        return found_nationalities

    def _calculate_country_mentions(self):
        # Count occurrences of countries in the original text
        # Note: The requirement says "count the number of mentions of different countries in the text"
        # We use the list of countries found in the text to populate the OrderedDict
        for country in self.countries:
            # Count how many times the country name appears in the text
            # Using regex to ensure word boundaries
            count = len(re.findall(r'\b' + re.escape(country) + r'\b', self.text))
            if count > 0:
                self.country_mentions[country] = count
