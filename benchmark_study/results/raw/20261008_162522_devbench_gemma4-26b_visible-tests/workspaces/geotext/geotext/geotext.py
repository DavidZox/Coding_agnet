import os
import re
from collections import OrderedDict, namedtuple

def get_data_path(path):
    """Constructs a file path by joining the root directory with a given path."""
    # Assuming the script is in geotext/geotext.py, the root is one level up.
    # The data_file is inside the geotext directory.
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, path)

def read_table(filename, usecols, sep='\t', comment='', encoding='utf-8', skip=0):
    """Parses data files and returns a dictionary mapping terms to their values."""
    data_dict = {}
    full_path = get_data_path(filename)
    
    if not os.path.exists(full_path):
        return data_dict

    with open(full_path, 'r', encoding=encoding, newline=None) as f:
        # Use a generator or loop to avoid reading the whole file into memory at once
        for i, line in enumerate(f):
            if i < skip:
                continue
            if not line.strip() or line.startswith(comment):
                continue
            
            parts = line.strip().split(sep)
            
            # We need a way to map this to the requested dictionary format.
            # Based on the requirement "mapping terms to their corresponding values",
            # we'll assume the first column in usecols is the key.
            if len(usecols) > 0:
                key_idx = usecols[0]
                if key_idx < len(parts):
                    key = parts[key_idx]
                    if len(usecols) == 1:
                        data_dict[key] = key
                    else:
                        # Return a tuple of the requested columns for the value
                        values = []
                        for col_idx in usecols[1:]:
                            if col_idx < len(parts):
                                values.append(parts[col_idx])
                            else:
                                values.append(None)
                        data_dict[key] = tuple(values)
            
    return data_dict

def build_index():
    """Loads data from text files and creates an index of nationalities, cities, and countries."""
    
    # 1. Load Country Info
    # countryInfo.txt: AD (0), AND (1), ..., Andorra (4), ...
    # We need a mapping of ISO -> Name
    # Based on architecture, data_file is inside geotext/
    countries = {} # ISO -> Name
    
    country_info_path = get_data_path('data_file/countryInfo.txt')
    if os.path.exists(country_info_path):
        with open(country_info_path, 'r', encoding='utf-8', newline=None) as f:
            for line in f:
                if not line.strip(): continue
                parts = line.strip().split('\t')
                if len(parts) > 4:
                    iso = parts[0].lower()
                    name = parts[4]
                    countries[iso] = name

    # 2. Load Nationalities
    # nationalities.txt: afghan:AF
    # Since read_table uses sep, and nationalities uses ':', we handle it manually or adjust
    nationalities = {} # nationality_name -> ISO
    nat_path = get_data_path('data_file/nationalities.txt')
    if os.path.exists(nat_path):
        with open(nat_path, 'r', encoding='utf-8', newline=None) as f:
            for line in f:
                if not line.strip(): continue
                parts = line.strip().split(':')
                if len(parts) == 2:
                    nationalities[parts[0].lower()] = parts[1].lower()

    # 3. Load Cities
    # cities15000.txt: 2081986 (0), Palikir... (1), ..., FM (11)
    # We need a mapping of City Name -> Country Code
    # Using read_table for cities. We need col 1 (name) and col 11 (country code)
    # However, read_table returns a dict where key is col[0], which is ID.
    # We'll use a custom approach to get Name -> Code.
    cities = {} # City Name -> Country Code
    # cities15000.txt: 2081986 (0), Palikir... (1), ..., FM (11)
    cities_path = get_data_path('data_file/cities15000.txt')
    if os.path.exists(cities_path):
        with open(cities_path, 'r', encoding='utf-8', newline=None) as f:
            for line in f:
                if not line.strip(): continue
                parts = line.strip().split('\t')
                if len(parts) > 11:
                    # The city name is in parts[1]. 
                    # Note: parts[1] might contain extra info like "Palikir - National Government Center"
                    # but for the purpose of this library, we take the full string in parts[1].
                    # We also need to handle the aliases in parts[2].
                    
                    # Handle parts[1] (main name)
                    main_name = parts[1].split(' - ')[0].strip().lower()
                    country_code = parts[11].lower()
                    
                    # Add main name
                    if main_name in cities:
                        if isinstance(cities[main_name], list):
                            if country_code not in cities[main_name]:
                                cities[main_name].append(country_code)
                        else:
                            if cities[main_name] != country_code:
                                cities[main_name] = [cities[main_name], country_code]
                            else:
                                pass # already exists
                    else:
                        cities[main_name] = country_code
                    
                    # Handle parts[2] (aliases)
                    if len(parts) > 2:
                        aliases = parts[2].split(',')
                        for alias in aliases:
                            alias = alias.strip().lower()
                            if not alias: continue
                            if alias in cities:
                                if isinstance(cities[alias], list):
                                    if country_code not in cities[alias]:
                                        cities[alias].append(country_code)
                                else:
                                    if cities[alias] != country_code:
                                        cities[alias] = [cities[alias], country_code]
                            else:
                                cities[alias] = country_code

    # 4. Load City Patches
    # citypatches.txt: oklahoma (0), US (1)
    patches = read_table('data_file/citypatches.txt', usecols=[0, 1])
    for city, info in patches.items():
        city_lower = city.lower()
        if info and isinstance(info, tuple) and len(info) > 0:
            country = info[0].lower()
            if country:
                # Patches can add to existing or overwrite.
                if city_lower in cities:
                    if isinstance(cities[city_lower], list):
                        if country not in cities[city_lower]:
                            cities[city_lower].append(country)
                    else:
                        if cities[city_lower] != country:
                            cities[city_lower] = [cities[city_lower], country]
                else:
                    cities[city_lower] = country

    Index = namedtuple('Index', ['cities', 'countries', 'nationalities'])
    return Index(cities=cities, countries=countries, nationalities=nationalities)

class GeoText:
    def __init__(self, text, country=None):
        self.text = text
        self.country = country
        self.countries = []
        self.cities = []
        self.nationalities = []
        self.country_mentions = OrderedDict()
        
        # Load index (In a real production app, this should be cached/singleton)
        self.index = build_index()
        
        # Pre-compile regex for word boundaries
        # This is a placeholder for the actual extraction logic
        self.city_regex = re.compile(r'\b[A-Za-z\u00C0-\u017F]+\b')

        # Run extraction pipeline
        candidates = self._find_candidates(text)
        self.countries = self._extract_countries(candidates)
        self.cities = self._extract_cities(candidates, country)
        self.nationalities = self._extract_nationalities(candidates)
        self._calculate_country_mentions()

    def _find_candidates(self, text):
        all_known_names = set(self.index.cities.keys()) | \
                          set(self.index.countries.values()) | \
                          set(self.index.countries.keys()) | \
                          set(self.index.nationalities.keys())
        
        sorted_names = sorted(list(all_known_names), key=len, reverse=True)
        
        found_candidates = []
        for name in sorted_names:
            pattern = re.escape(name)
            # Use a simple finditer without \b to avoid Unicode boundary issues.
            # We will handle word boundaries using the 'claimed' logic and checking surrounding characters.
            for match in re.finditer(pattern, text, re.IGNORECASE):
                start, end = match.start(), match.end()
                
                # Check boundaries manually: character before and after should not be alphanumeric
                # We use a regex to check if the character at start-1 or end is a "word" character.
                # In Python 3, \w is Unicode-aware.
                before_ok = True
                if start > 0:
                    if re.match(r'\w', text[start-1]):
                        before_ok = False
                
                after_ok = True
                if end < len(text):
                    if re.match(r'\w', text[end]):
                        after_ok = False
                
                if before_ok and after_ok:
                    found_candidates.append((start, end, match.group()))
        
        if not found_candidates:
            return []

        # Sort by length descending to prioritize longer matches
        found_candidates.sort(key=lambda x: len(x[2]), reverse=True)
        
        claimed = [False] * len(text)
        final_candidates = []
        
        for start, end, original_text_slice in found_candidates:
            if not any(claimed[start:end]):
                final_candidates.append((start, end, original_text_slice))
                for i in range(start, end):
                    claimed[i] = True
        
        # Sort by position to maintain original text order
        final_candidates.sort(key=lambda x: x[0])
        return [item[2] for item in final_candidates]

    def _extract_countries(self, candidates):
        found_countries = []
        # The index keys (ISO) and values (Names) are stored in lowercase in build_index
        for cand in candidates:
            cand_lower = cand.lower()
            # Check if it's a country name
            for iso_lower, name in self.index.countries.items():
                if name.lower() == cand_lower or iso_lower == cand_lower:
                    found_countries.append(name)
                    break
        return found_countries

    def _extract_cities(self, candidates, country_code):
        found_cities = []
        target_country = country_code.lower() if country_code else None
        for cand in candidates:
            cand_lower = cand.lower()
            if cand_lower in self.index.cities:
                city_country = self.index.cities[cand_lower]
                # city_country can be a string or a list of strings
                if isinstance(city_country, list):
                    if target_country is None or target_country in [c.lower() for c in city_country]:
                        found_cities.append(cand)
                else:
                    if target_country is None or city_country.lower() == target_country:
                        found_cities.append(cand)
        return found_cities

    def _extract_nationalities(self, candidates):
        found_nationalities = []
        for cand in candidates:
            if cand.lower() in self.index.nationalities:
                found_nationalities.append(cand)
        return found_nationalities

    def _calculate_country_mentions(self):
        # name_to_iso needs to handle case-insensitive lookup
        name_to_iso = {name.lower(): iso for iso, name in self.index.countries.items()}
        iso_to_name = {iso.lower(): name for iso, name in self.index.countries.items()}
        
        for c in self.countries:
            c_lower = c.lower()
            iso = None
            if c_lower in name_to_iso:
                iso = name_to_iso[c_lower]
            elif c_lower in iso_to_name:
                iso = iso_to_name[c_lower]
            
            if iso:
                # The requirement says OrderedDict, and we should use the ISO code as key.
                # The test expects 'US' or 'CN' (uppercase).
                iso_upper = iso.upper()
                self.country_mentions[iso_upper] = self.country_mentions.get(iso_upper, 0) + 1
