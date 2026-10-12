import os
import re
from collections import OrderedDict, Counter
from collections import namedtuple

# Define the Index namedtuple as per architecture design
Index = namedtuple('Index', ['nationalities', 'cities', 'countries'])

def get_data_path(path):
    """
    Constructs a file path by joining the root directory with a given path.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, path)

def read_table(filename, usecols=None, sep='\t', comment='', encoding='utf-8', skip=0):
    """
    Parses data files to create dictionaries mapping terms to their corresponding values.
    """
    data = {}
    path = get_data_path(os.path.join('geotext', 'data_file', filename))
    
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
            # However, for this specific project, we map the first column to the rest or specific logic
            # Based on the data files:
            # nationalities.txt: term:code -> {term: code}
            # countryInfo.txt: ISO, ..., Country, ... -> {Country: ISO}
            # cities15000.txt: ... City, ... CountryCode -> {City: CountryCode}
            # citypatches.txt: patch, CountryCode -> {patch: CountryCode}
            
            if filename == 'nationalities.txt':
                # format: afghan:AF
                if ':' in line:
                    term, code = line.split(':', 1)
                    data[term.strip()] = code.strip()
            elif filename == 'countryInfo.txt':
                # format: AD AND ... Andorra ...
                # We need to find the Country name. Based on example: AD(0) AND(1) ... Andorra(4)
                # Since usecols isn't strictly defined in the prompt for indices, 
                # we assume the function is a generic parser.
                # For the purpose of build_index, we will handle the logic inside build_index or here.
                # Let's assume usecols provides indices of columns to keep.
                if usecols:
                    row = {i: parts[i] for i in usecols if i < len(parts)}
                    # This is a simplified version; real implementation depends on specific column mapping
                    # For this task, we'll return the parts to be processed by build_index
                    pass 
            
            # To satisfy the requirement of "creating dictionaries mapping terms to values"
            # we implement a flexible version.
            if filename == 'citypatches.txt':
                # format: oklahoma US
                if len(parts) >= 2:
                    data[parts[0].strip()] = parts[1].strip()
            elif filename == 'cities15000.txt':
                # format: ID Name... City,City,City... CountryCode
                # The city name is usually in the second or third column.
                # Based on example: 2081986 (0) Palikir... (1) Palakir... (2) ... FM (last)
                if len(parts) >= 2:
                    # We'll use the second column as the primary city name for the index
                    # and the last column as the country code.
                    data[parts[1].strip()] = parts[-1].strip()
            elif filename == 'countryInfo.txt':
                # Based on example: AD(0) AND(1) ... Andorra(4)
                # We want Country -> ISO
                if len(parts) >= 5:
                    data[parts[4].strip()] = parts[0].strip()

    return data

def build_index():
    """
    Loads data from text files and creates an index of nationalities, cities, and countries.
    """
    # 1. Nationalities
    nat_data = read_table('nationalities.txt')
    
    # 2. Countries (Country Name -> ISO)
    # We need to parse countryInfo.txt specifically to get Country -> ISO
    country_map = {}
    path = get_data_path(os.path.join('geotext', 'data_file', 'countryInfo.txt'))
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('\t')
            if len(parts) >= 5:
                country_map[parts[4]] = parts[0] # Country: ISO

    # 3. Cities (City Name -> Country Code)
    city_map = read_table('cities15000.txt')
    
    # 4. City Patches (Patch -> Country Code)
    patch_map = read_table('citypatches.txt')
    # Merge patches into city_map
    city_map.update(patch_map)

    return Index(
        nationalities=nat_data,
        cities=city_map,
        countries=country_map
    )

# Global index instance (singleton-like pattern for the library)
_INDEX = None

class GeoText:
    def __init__(self, text, country=None):
        self.text = text
        self.country = country
        self.countries = []
        self.cities = []
        self.nationalities = []
        self.country_mentions = OrderedDict()
        
        global _INDEX
        if _INDEX is None:
            _INDEX = build_index()
            
        self._city_regex = None # Initialized during processing
        
        self._process()

    def _process(self):
        candidates = self._find_candidates(self.text)
        self.countries = self._extract_countries(candidates)
        self.cities = self._extract_cities(candidates, self.country)
        self.nationalities = self._extract_nationalities(candidates)
        self._calculate_country_mentions()

    def _find_candidates(self, text):
        # Split text into words/tokens, removing punctuation
        # A simple way is to use regex to find words
        return re.findall(r'\b\w+\b', text)

    def _extract_countries(self, candidates):
        found = []
        for word in candidates:
            if word in _INDEX.countries:
                found.append(word)
        return found

    def _extract_cities(self, candidates, country_code):
        found = []
        for word in candidates:
            if word in _INDEX.cities:
                # Check if city belongs to the specified country if country_code is provided
                if country_code:
                    if _INDEX.cities[word] == country_code:
                        found.append(word)
                else:
                    found.append(word)
        return found

    def _extract_nationalities(self, candidates):
        found = []
        for word in candidates:
            if word in _INDEX.nationalities:
                found.append(word)
        return found

    def _calculate_country_mentions(self):
        # Count occurrences of country names in the text
        # We use the list of countries found in the text
        counts = Counter(self.countries)
        self.country_mentions = OrderedDict(counts.most_common())
