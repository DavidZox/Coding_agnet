import os
import re
from collections import OrderedDict, namedtuple

def get_data_path(path):
    """Constructs a file path by joining the root directory with a given path."""
    # Assuming the data_file directory is relative to this file's location
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, path)

def read_table(filename, usecols, sep='\t', comment='#', encoding='utf-8', skip=0):
    """Parses data files to create dictionaries mapping terms to their corresponding values."""
    data_path = get_data_path(os.path.join('geotext', 'data_file', filename))
    table = {}
    try:
        with open(data_path, 'r', encoding=encoding) as f:
            lines = f.readlines()[skip:]
            for line in lines:
                line = line.strip()
                if not line or line.startswith(comment):
                    continue
                parts = line.split(sep)
                
                # Create a dictionary for the row based on usecols indices
                row_dict = {}
                for col_idx in usecols:
                    if col_idx < len(parts):
                        row_dict[col_idx] = parts[col_idx].strip()
                
                # To satisfy the requirement of "mapping terms to values",
                # we use the first specified column as the key and the rest as the value.
                if row_dict:
                    key = row_dict[usecols[0]]
                    value = {idx: val for idx, val in row_dict.items() if idx != usecols[0]}
                    table[key] = value
    except FileNotFoundError:
        pass
    return table

def build_index():
    """Loads data from text files and creates an index of nationalities, cities, and countries."""
    Index = namedtuple('Index', ['nationalities', 'cities', 'countries'])
    
    # nationalities.txt: term:country_code -> nationalities[term] = country_code
    # Example: afghan:AF
    nationalities = {}
    try:
        data_path = get_data_path(os.path.join('geotext', 'data_file', 'nationalities.txt'))
        with open(data_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if ':' in line:
                    term, country_code = line.split(':', 1)
                    nationalities[term] = country_code
    except FileNotFoundError:
        pass

    # cities15000.txt: city_name -> country_code
    # Example: 2081986	Palikir...	6.92477	158.16109	P	PPLC	FM...
    # Based on the example, city name is index 2, country code is index 6 (FM)
    # However, the PRD says "city_name -> country_code". 
    # Let's use read_table logic or direct parsing.
    cities = {}
    try:
        # Using read_table to get city_name (index 2) -> country_code (index 6)
        # Note: The example shows index 2 is the name, index 6 is the code.
        city_data = read_table('cities15000.txt', usecols=[2, 6])
        for city_name, info in city_data.items():
            if 6 in info:
                cities[city_name] = info[6]
    except Exception:
        pass

    # countryInfo.txt: country_code -> country_name
    # Example: AD	AND	020	AN	Andorra...
    # ISO code is index 0, Country name is index 4
    countries = {}
    try:
        country_data = read_table('countryInfo.txt', usecols=[0, 4])
        for code, info in country_data.items():
            if 4 in info:
                countries[code] = info[4]
    except Exception:
        pass

    # citypatches.txt: city_name -> country_code
    # Example: oklahoma	US
    try:
        patch_data = read_table('citypatches.txt', usecols=[0, 1])
        for city_name, info in patch_data.items():
            if 1 in info:
                cities[city_name] = info[1]
    except Exception:
        pass
    
    return Index(nationalities=nationalities, cities=cities, countries=countries)

# Global index instance
INDEX = build_index()

class GeoText:
    def __init__(self, text, country=None):
        self.text = text
        self.country = country
        self.countries = []
        self.cities = []
        self.nationalities = []
        self.country_mentions = OrderedDict()
        
        # Placeholder for regex
        self.city_regex = re.compile(r'\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b')
        
        # The sequence of operations as per UML
        self._find_candidates()
        self._extract_countries(self._candidates)
        self._extract_cities(self._candidates, self.country)
        self._extract_nationalities(self._candidates)
        self._calculate_country_mentions()

    def _find_candidates(self):
        # Use regex to find potential place names (capitalized words)
        self._candidates = self.city_regex.findall(self.text)

    def _extract_countries(self, candidates):
        # Extract country names from candidates by checking against INDEX.countries
        # Note: INDEX.countries is {code: name}
        found_countries = []
        for candidate in candidates:
            for code, name in INDEX.countries.items():
                if candidate == name:
                    found_countries.append(name)
                    break
        self.countries = list(dict.fromkeys(found_countries))

    def _extract_cities(self, candidates, country):
        # Extract city names from candidates, optionally filtered by country code
        found_cities = []
        for candidate in candidates:
            if candidate in INDEX.cities:
                city_country_code = INDEX.cities[candidate]
                if country is None or city_country_code == country:
                    found_cities.append(candidate)
        self.cities = list(dict.fromkeys(found_cities))

    def _extract_nationalities(self, candidates):
        # Extract nationalities from candidates
        found_nationalities = []
        for candidate in candidates:
            if candidate in INDEX.nationalities:
                found_nationalities.append(candidate)
        self.nationalities = list(dict.fromkeys(found_nationalities))

    def _calculate_country_mentions(self):
        # Count mentions of countries in the text
        # We need to check every word/candidate against country names
        # and count how many times they appear in the original text.
        # However, the requirement is to count mentions of different countries.
        # We'll iterate through the text and check if any country name is present.
        
        # To avoid partial matches, we use word boundaries
        for code, name in INDEX.countries.items():
            # Find all occurrences of the country name in the text
            pattern = r'\b' + re.escape(name) + r'\b'
            matches = re.findall(pattern, self.text)
            if matches:
                self.country_mentions[name] = len(matches)
