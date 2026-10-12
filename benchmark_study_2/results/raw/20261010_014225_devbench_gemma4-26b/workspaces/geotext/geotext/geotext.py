import os
import re
from collections import namedtuple, OrderedDict

# Define the namedtuple for the index
Index = namedtuple('Index', ['nationalities', 'cities', 'countries', 'citypatches'])

def get_data_path(path):
    """
    Constructs a file path by joining the root directory with a given path.
    """
    # Assuming the script is run from the project root or the package directory
    # We find the directory where geotext.py is located
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, path)

def read_table(filename, usecols=None, sep='\t', comment='', encoding='utf-8', skip=0):
    """
    Parses data files and creates a dictionary mapping terms to their corresponding values.
    """
    data_dict = {}
    path = get_data_path(filename)
    
    if not os.path.exists(path):
        return data_dict

    with open(path, 'r', encoding=encoding) as f:
        lines = f.readlines()[skip:]
        for line in lines:
            line = line.strip()
            if not line or line.startswith(comment):
                continue
            
            parts = line.split(sep)
            
            # If usecols is provided, we only care about those indices
            if usecols is not None:
                # Filter parts based on usecols
                # Note: This implementation assumes usecols are indices
                row = {}
                for idx in usecols:
                    if idx < len(parts):
                        row[idx] = parts[idx]
                    else:
                        row[idx] = None
                
                # For the purpose of this library, we usually map a key to a value
                # We'll assume the first requested column is the key
                key_idx = usecols[0]
                if key_idx in row and row[key_idx]:
                    key = row[key_idx]
                    # If there's only one column requested, value is the key itself or None
                    # But typically we want to map key -> value
                    if len(usecols) > 1:
                        val_idx = usecols[1]
                        data_dict[key] = row[val_idx] if row[val_idx] else key
                    else:
                        data_dict[key] = key
            else:
                # Default behavior: if no usecols, we can't easily know what to map.
                # However, based on the requirements, read_table is used to create mappings.
                pass
                
    return data_dict

def build_index():
    """
    Loads data from text files and creates an index.
    """
    # 1. Load nationalities: 'afghan:AF' -> {'afghan': 'AF'}
    nationalities = {}
    nat_path = get_data_path('data_file/nationalities.txt')
    if os.path.exists(nat_path):
        with open(nat_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and ':' in line:
                    term, code = line.split(':', 1)
                    nationalities[term.lower()] = code

    # 2. Load countries: 'AD\tAND\t... \tAndorra\t...'
    # We need a mapping of ISO code -> Country Name and Country Name -> ISO code
    # Based on architecture, we need to find countries in text.
    # Let's build: country_name -> iso_code and iso_code -> country_name
    countries_info = {} # iso_code -> country_name
    country_name_to_iso = {} # country_name -> iso_code
    
    country_path = get_data_path('data_file/countryInfo.txt')
    if os.path.exists(country_path):
        with open(country_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split('\t')
                if len(parts) > 4:
                    iso_code = parts[0]
                    country_name = parts[4]
                    countries_info[iso_code] = country_name
                    country_name_to_iso[country_name] = iso_code

    # 3. Load cities: '2081986\tPalikir...\t... \tFM'
    # We need a mapping of city_name -> country_code
    # The format in cities15000.txt: id, name1, name2, names_list, lat, lon, etc... country_code is usually at a specific index.
    # Looking at the example: '2081986\tPalikir...\t... \tFM'
    # The example shows FM is the 11th element (index 10) if we count carefully.
    # Actually, the example provided: 2081986 (0) Palikir (1) Palikir (2) Palakir... (3) 6.92477 (4) 158.16109 (5) P (6) PPLC (7) FM (8)
    # Let's assume the country code is at index 8 for this specific file format.
    cities = {}
    city_path = get_data_path('data_file/cities15000.txt')
    if os.path.exists(city_path):
        with open(city_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split('\t')
                if len(parts) > 8:
                    country_code = parts[8]
                    # The city names are in parts[1], parts[2], and the comma-separated list in parts[3]
                    # We should index all of them
                    city_names = [parts[1], parts[2]]
                    # Split the comma separated names in parts[3]
                    extra_names = parts[3].split(',')
                    city_names.extend(extra_names)
                    
                    for name in city_names:
                        name = name.strip()
                        if name:
                            cities[name.lower()] = country_code

    # 4. Load city patches: 'oklahoma\tUS'
    citypatches = {}
    patch_path = get_data_path('data_file/citypatches.txt')
    if os.path.exists(patch_path):
        with open(patch_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and '\t' in line:
                    city, country = line.split('\t', 1)
                    citypatches[city.lower()] = country

    return Index(
        nationalities=nationalities,
        cities=cities,
        countries=country_name_to_iso,
        citypatches=citypatches
    )

class GeoText:
    def __init__(self, text, country=None):
        self.text = text
        self.country = country
        self.countries = []
        self.cities = []
        self.nationalities = []
        self.country_mentions = OrderedDict()
        
        # Load index
        self._index = build_index()
        
        # Perform extraction
        candidates = self._find_candidates(text)
        self._extract_countries(candidates)
        self._extract_cities(candidates, country)
        self._extract_nationalities(candidates)
        self._calculate_country_mentions()

    def _find_candidates(self, text):
        # Simple candidate finding: split by whitespace and remove punctuation
        # In a real implementation, this would use a regex or NLP
        words = re.findall(r'\b\w+\b', text)
        return words

    def _extract_countries(self, candidates):
        # Check if any candidate is a country name in our index
        # Note: candidates are words, but country names can be multiple words.
        # For this implementation, we'll check if the text contains the country name.
        for country_name, iso_code in self._index.countries.items():
            # Use regex to find whole word matches of the country name
            pattern = r'\b' + re.escape(country_name) + r'\b'
            if re.search(pattern, self.text, re.IGNORECASE):
                self.countries.append(country_name)

    def _extract_cities(self, candidates, country_code):
        # Check city names against the index
        # We iterate through the text to find matches for city names
        
        # First, check patches
        for patch_city, patch_country in self._index.citypatches.items():
            if country_code and patch_country != country_code:
                continue
            
            pattern = r'\b' + re.escape(patch_city) + r'\b'
            if re.search(pattern, self.text, re.IGNORECASE):
                self.cities.append(patch_city.capitalize())

        # Then, check regular cities
        for city_name, c_code in self._index.cities.items():
            # If country filter is provided, only match if country code matches
            if country_code and c_code != country_code:
                continue
            
            # Avoid duplicates if already added via patch
            if city_name.capitalize() in self.cities:
                continue

            pattern = r'\b' + re.escape(city_name) + r'\b'
            if re.search(pattern, self.text, re.IGNORECASE):
                self.cities.append(city_name.capitalize())

    def _extract_nationalities(self, candidates):
        for nat_name, iso_code in self._index.nationalities.items():
            pattern = r'\b' + re.escape(nat_name) + r'\b'
            if re.search(pattern, self.text, re.IGNORECASE):
                self.nationalities.append(nat_name)

    def _calculate_country_mentions(self):
        # Count how many times each country name appears in the text
        for country_name in self._index.countries.keys():
            pattern = r'\b' + re.escape(country_name) + r'\b'
            matches = re.findall(pattern, self.text, re.IGNORECASE)
            if matches:
                self.country_mentions[country_name] = len(matches)
