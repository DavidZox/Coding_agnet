import os
import re
from collections import OrderedDict, namedtuple

def get_data_path(path):
    """
    Constructs a file path by joining the root directory with a given path.
    """
    # The data files are in geotext/data_file relative to this file
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, path)

def read_table(filename, usecols, sep='\t', comment='', encoding='utf-8', skip=0):
    """
    Parses data files and creates dictionaries mapping terms to their corresponding values.
    """
    data_dict = {}
    path = get_data_path(filename)
    
    if not os.path.exists(path):
        return data_dict

    with open(path, 'r', encoding=encoding) as f:
        lines = f.readlines()[skip:]
        for line in lines:
            line = line.strip('\n\r')
            if not line or line.startswith(comment):
                continue
            
            parts = line.split(sep)
            # Create a dictionary for the current row based on usecols indices
            row_data = {}
            for col_idx in usecols:
                if col_idx < len(parts):
                    row_data[col_idx] = parts[col_idx].strip()
            
            if row_data:
                # We assume the first requested column is the key, 
                # and we store the rest of the requested columns as values.
                # However, the requirement says "mapping terms to their corresponding values".
                # Based on typical usage for this library:
                # key = parts[usecols[0]], value = parts[usecols[1]] (if exists)
                key = parts[usecols[0]]
                if len(usecols) > 1:
                    val = parts[usecols[1]]
                    data_dict[key] = val
                else:
                    data_dict[key] = True # Just mark existence
                    
    return data_dict

def build_index():
    """
    Loads data from text files and creates an index of nationalities, cities, and countries.
    Returns a namedtuple containing these indices.
    """
    # 1. Load Countries
    # countryInfo.txt: AD (0), AND (1), ..., Andorra (4)
    # We want a mapping of Country Name -> ISO Code (or vice versa)
    # Looking at the requirement: "extracting cities by country codes"
    # and "count mentions of different countries".
    # Usually, we need: 
    # - country_code_to_name: {'AD': 'Andorra'}
    # - country_name_to_code: {'Andorra': 'AD'}
    # - country_names: set of names for regex
    
    # Using direct reading to avoid read_table issues with countryInfo.txt
    country_info = {}
    country_path = get_data_path('data_file/countryInfo.txt')
    if os.path.exists(country_path):
        with open(country_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip('\n\r')
                if not line:
                    continue
                parts = line.split('\t')
                if len(parts) > 4:
                    code = parts[0].strip()
                    name = parts[4].strip()
                    country_info[code] = name

    # Reverse for name lookup
    name_to_code = {v: k for k, v in country_info.items()}
    # Also keep codes for filtering
    code_to_name = country_info
    
    # 2. Load Nationalities
    # nationalities.txt: afghan:AF
    nationalities_dict = {}
    nat_path = get_data_path('data_file/nationalities.txt')
    if os.path.exists(nat_path):
        with open(nat_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and ':' in line:
                    nat, code = line.split(':')
                    nationalities_dict[nat.lower()] = code.upper()

    # 3. Load Cities
    # cities15000.txt: 2081986 (0), Name (1), ... Country Code (6)
    # We need a way to check if a city belongs to a country.
    # A dict: {city_name: [country_code, ...]}
    cities_dict = {}
    cities_path = get_data_path('data_file/cities15000.txt')
    if os.path.exists(cities_path):
        with open(cities_path, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.split('\t')
                if len(parts) > 6:
                    city_name = parts[1].strip()
                    country_code = parts[6].strip()
                    if city_name not in cities_dict:
                        cities_dict[city_name] = []
                    if country_code not in cities_dict[city_name]:
                        cities_dict[city_name].append(country_code)

    # 4. Load City Patches
    # citypatches.txt: oklahoma (0), US (1)
    patches = read_table('data_file/citypatches.txt', usecols=[0, 1])
    for city, code in patches.items():
        if city not in cities_dict:
            cities_dict[city] = []
        if code not in cities_dict[city]:
            cities_dict[city].append(code)

    Index = namedtuple('Index', ['cities', 'countries', 'nationalities'])
    return Index(
        cities=cities_dict, 
        countries=name_to_code, # name -> code
        nationalities=nationalities_dict # name -> code
    )

class GeoText:
    def __init__(self, text, country=None):
        self.text = text
        self.country = country
        
        # Load index
        self.index = build_index()
        
        # Results
        self.countries = []
        self.cities = []
        self.nationalities = []
        self.country_mentions = OrderedDict()
        
        # Internal regex (to be defined during extraction)
        self.city_regex = None
        
        # Run extraction pipeline
        candidates = self._find_candidates()
        self._extract_countries(candidates)
        self._extract_cities(candidates, country)
        self._extract_nationalities(candidates)
        self._calculate_country_mentions()

    def _find_candidates(self):
        # Use regex to find all words/tokens, including those with non-ASCII characters
        # We use a pattern that captures words and sequences of words separated by spaces
        # This helps in finding multi-word names like "Rio de Janeiro"
        # We use a regex that captures sequences of characters that are not whitespace or punctuation
        return re.findall(r'[^\s\.,!?;:\"\'\(\)\[\]\{\}]+', self.text)

    def _is_full_word(self, sub_candidate):
        # Ensure the sub_candidate is a full word/phrase in the original text
        # using word boundaries to avoid partial matches like "London" in "Londonderry"
        # We clean the sub_candidate for the regex pattern to handle punctuation
        clean_sub = re.sub(r'[^\w\s]', '', sub_candidate).strip()
        if not clean_sub:
            return False
        # Use word boundaries \b. Note: \b works for ASCII. 
        # For Unicode, we rely on the fact that clean_sub is stripped of punctuation.
        # We use a pattern that looks for the cleaned string surrounded by non-word characters or boundaries.
        pattern = rf'(?<![\w]){re.escape(clean_sub)}(?![\w])'
        return re.search(pattern, self.text, re.UNICODE) is not None

    def _extract_countries(self, candidates):
        found_countries = []
        n = len(candidates)
        i = 0
        while i < n:
            found_in_this_pos = False
            for length in range(min(4, n - i), 0, -1):
                sub_candidate = " ".join(candidates[i:i+length])
                # Clean sub_candidate for matching with index keys
                clean_sub = re.sub(r'[^\w\s]', '', sub_candidate).strip()
                if clean_sub in self.index.countries:
                    if self._is_full_word(sub_candidate):
                        found_countries.append(clean_sub)
                        i += length
                        found_in_this_pos = True
                        break
            if not found_in_this_pos:
                i += 1
        self.countries = found_countries

    def _extract_cities(self, candidates, country):
        found_cities = []
        n = len(candidates)
        i = 0
        while i < n:
            found_in_this_pos = False
            for length in range(min(5, n - i), 0, -1):
                sub_candidate = " ".join(candidates[i:i+length])
                # Clean sub_candidate for matching with index keys
                clean_sub = re.sub(r'[^\w\s]', '', sub_candidate).strip()
                if clean_sub in self.index.cities:
                    if self._is_full_word(sub_candidate):
                        city_codes = self.index.cities[clean_sub]
                        match_country = True
                        if country:
                            target_code = country
                            if country in self.index.countries:
                                target_code = self.index.countries[country]
                            if target_code not in city_codes:
                                match_country = False
                        
                        if match_country:
                            found_cities.append(clean_sub)
                            i += length
                            found_in_this_pos = True
                            break
            if not found_in_this_pos:
                i += 1
        self.cities = found_cities

    def _extract_nationalities(self, candidates):
        found_nationalities = []
        n = len(candidates)
        i = 0
        while i < n:
            found_in_this_pos = False
            for length in range(min(3, n - i), 0, -1):
                sub_candidate = " ".join(candidates[i:i+length])
                # Clean sub_candidate for matching with index keys
                clean_sub = re.sub(r'[^\w\s]', '', sub_candidate).strip()
                if clean_sub.lower() in self.index.nationalities:
                    if self._is_full_word(sub_candidate):
                        found_nationalities.append(clean_sub)
                        i += length
                        found_in_this_pos = True
                        break
            if not found_in_this_pos:
                i += 1
        self.nationalities = found_nationalities

    def _calculate_country_mentions(self):
        mentions = OrderedDict()
        
        # 1. Count from extracted countries
        for country_name in self.countries:
            code = self.index.countries.get(country_name)
            if code:
                mentions[code] = mentions.get(code, 0) + 1
        
        # 2. Count from extracted cities
        for city_name in self.cities:
            city_codes = self.index.cities.get(city_name, [])
            for code in city_codes:
                mentions[code] = mentions.get(code, 0) + 1
                
        # 3. Count from extracted nationalities
        for nat_name in self.nationalities:
            code = self.index.nationalities.get(nat_name.lower())
            if code:
                mentions[code] = mentions.get(code, 0) + 1
                
        self.country_mentions = mentions
