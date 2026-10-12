import os
from collections import OrderedDict
from typing import List, Dict, Any, Optional, NamedTuple
import re

# --- Index Structure Definition ---
# Based on the requirement to build an index containing nationality, city, and country info.
# We define a structure to hold the loaded data.

class CountryIndex(NamedTuple):
    """Stores country information: ISO codes, names, etc."""
    country_map: Dict[str, Dict[str, str]]  # Key: Country Name/Code, Value: {col_index: value}
    
class CityIndex(NamedTuple):
    """Stores city information: names and associated country codes."""
    city_country_map: Dict[str, str]  # Key: City Name, Value: Country Code

class NationalityIndex(NamedTuple):
    """Stores nationality mappings."""
    nationality_map: Dict[str, str]  # Key: Nationality Term, Value: Country Code/ISO

class GeoIndex(NamedTuple):
    """The complete index structure."""
    countries: CountryIndex
    cities: CityIndex
    nationalities: NationalityIndex

# Global variable to hold the built index, ensuring idempotency
_GLOBAL_INDEX: Optional[GeoIndex] = None

def get_data_path(path: str) -> str:
    """
    Constructs a full, absolute path to a data file within the geotext/data_file directory.

    Args:
        path: The relative path to the data file (e.g., 'cities15000.txt').

    Returns:
        The absolute path to the data file.
    """
    # Determine the directory of the current module/file
    # This helps in resolving paths correctly regardless of where the script is called from.
    current_dir = os.path.dirname(os.path.abspath(__file__))
    data_file_dir = os.path.join(current_dir, 'data_file')
    return os.path.join(data_file_dir, path)

def read_table(filename: str, usecols: List[int], sep: str = '\t', comment: str = '#', encoding: str = 'utf-8', skip: int = 0) -> Dict[Any, Dict[int, str]]:
    """
    Parses a data file from the data_file directory into a dictionary structure.

    The structure is {key_value: {column_index: column_value, ...}}

    Args:
        filename: The name of the data file (e.g., 'countryInfo.txt').
        usecols: A list of 0-based column indices to include in the resulting dictionary values.
        sep: The delimiter used in the file.
        comment: Lines starting with this string are skipped.
        encoding: The file encoding.
        skip: The number of initial lines to skip before reading data.

    Returns:
        A dictionary where keys are derived from the first column, and values are dictionaries
        containing the selected columns.
    """
    full_path = get_data_path(filename)
    data_map: Dict[Any, Dict[int, str]] = {}

    try:
        with open(full_path, 'r', encoding=encoding) as f:
            # Skip initial lines
            for _ in range(skip):
                next(f)
            
            for line in f:
                line = line.strip()
                if not line or line.startswith(comment):
                    continue
                
                fields = line.split(sep)
                
                if not fields:
                    continue

                # Use the first field as the primary key
                key = fields[0]
                
                # Build the inner dictionary containing only the specified columns
                row_data = {}
                for col_index in usecols:
                    if col_index < len(fields):
                        row_data[col_index] = fields[col_index]
                
                data_map[key] = row_data
                
    except FileNotFoundError:
        print(f"Error: Data file not found at {full_path}")
        return {}
    except Exception as e:
        print(f"An error occurred while reading {filename}: {e}")
        return {}
        
    return data_map

def build_index() -> GeoIndex:
    """
    Loads data from text files in the data_file directory and creates an index 
    of nationalities, cities, and countries in memory.

    This function is idempotent.

    Returns:
        GeoIndex: A namedtuple containing the compiled index data.
    """
    global _GLOBAL_INDEX
    
    if _GLOBAL_INDEX is not None:
        return _GLOBAL_INDEX

    print("Building GeoText index...")
    
    # 1. Load Nationalities (nationalities.txt: afghan:AF)
    # Key: Nationality Term (e.g., 'afghan'), Value: Country Code (e.g., 'AF')
    # Usecols: [0] (Term), [1] (Code)
    nationality_raw = read_table('nationalities.txt', usecols=[0, 1], sep=':', comment='#')
    nationality_map = {}
    for term, data in nationality_raw.items():
        # Assuming the structure is {term: {0: term, 1: code}}
        if 1 in data:
            nationality_map[term] = data[1]
            
    nationality_index = NationalityIndex(nationality_map=nationality_map)

    # 2. Load Country Info (countryInfo.txt: AD	AND	020	AN	Andorra...)
    # We need to map Country Name/Code to its details.
    # Assuming the first column is the ISO code (Key), and we want Name (Col 4) and ISO3 (Col 3)
    # Based on example: AD (0) | AND (1) | 020 (2) | AN (3) | Andorra (4)
    country_raw = read_table('countryInfo.txt', usecols=[0, 1, 2, 3, 4], sep='\t', comment='#')
    
    country_map: Dict[str, Dict[str, str]] = {}
    for iso_code, data in country_raw.items():
        # Store the data keyed by the ISO code (the first column)
        country_map[iso_code] = {
            'iso_code': data.get(0),
            'country_name': data.get(4),
            'iso3': data.get(3)
        }
    country_index = CountryIndex(country_map=country_map)

    # 3. Load Cities (cities15000.txt: 2081986	Palikir - National Government Center	...)
    # Assuming the city name is in the second column (index 1) and country code is in the last column (index 21, based on example structure)
    # Example: ... | 02 | SO (Index 21)
    city_raw = read_table('cities15000.txt', usecols=[1, 21], sep='\t', comment='#')
    
    city_country_map: Dict[str, str] = {}
    for city_name, data in city_raw.items():
        # Key: City Name (Col 1), Value: Country Code (Col 21)
        if 1 in data and 21 in data:
            city_country_map[data[1]] = data[21]
        
    city_index = CityIndex(city_country_map=city_country_map)

    # Compile the final index
    final_index = GeoIndex(
        countries=country_index,
        cities=city_index,
        nationalities=nationality_index
    )
    
    _GLOBAL_INDEX = final_index
    print("Index building complete.")
    return final_index


# Placeholder for GeoText class structure as per UML_class.md
class GeoText:
    """
    A class designed to extract city and country mentions from text.
    """
    def __init__(self, text: str, country: Optional[str] = None):
        self.text = text
        self.country = country
        self.countries: List[str] = []
        self.cities: List[str] = []
        self.nationalities: List[str] = []
        self.country_mentions: OrderedDict = OrderedDict()
        self._city_regex: Optional[re.Pattern] = None
        self._candidates: List[str] = []
        
        # Initialize regex pattern for candidate finding (a simple placeholder regex)
        # In a real implementation, this regex would be complex and derived from data/requirements.
        # For this step, we use a broad pattern to capture potential place names.
        self._city_regex = re.compile(r'\b[A-Z][a-z]+(?:[\s-][A-Z][a-z]+)*\b')
        
        self._find_candidates(text)
        self._extract_countries(self._candidates)
        self._extract_cities(self._candidates, country)
        self._extract_nationalities(self._candidates)
        self._calculate_country_mentions()

    # Placeholder methods matching UML_sequence.md flow
    def _find_candidates(self, text: str):
        """
        Uses regex to find all potential geographical name candidates in the text.
        """
        # Find all matches using the initialized regex
        self._candidates = self._city_regex.findall(text)
        # In a real scenario, this would involve more sophisticated tokenization and matching
        # against known names or patterns.
        pass
    
    def _extract_countries(self, candidates: List[str]):
        """
        Filters candidate list to extract actual country names using the global index.
        """
        if _GLOBAL_INDEX is None:
            print("Error: Index not built. Cannot extract countries.")
            return

        country_map = _GLOBAL_INDEX.countries.country_map
        
        # Simple heuristic: Check if the candidate matches any known country name in the index
        found_countries = set()
        for candidate in candidates:
            # Check if the candidate (or a normalized version) exists as a key in the country map
            # This assumes country names in the text match the names in countryInfo.txt (Col 4)
            # We iterate over the values of country_map to get the actual country names
            for key, data in country_map.items():
                if data.get('country_name') and candidate.lower() == data['country_name'].lower():
                    found_countries.add(data['country_name'])
                    break
        
        self.countries = list(found_countries)
        
    def _extract_cities(self, candidates: List[str], country: Optional[str]):
        """
        Filters candidate list to extract actual city names, optionally filtered by country code.
        """
        if _GLOBAL_INDEX is None:
            print("Error: Index not built. Cannot extract cities.")
            return

        city_country_map = _GLOBAL_INDEX.cities.city_country_map
        
        found_cities = set()
        
        for candidate in candidates:
            # Check if the candidate exists as a city name in the index
            if candidate in city_country_map:
                city_code = city_country_map[candidate]
                
                # Apply country filtering if 'country' parameter is provided
                if country is None or city_code == country:
                    found_cities.add(candidate)
        
        self.cities = list(found_cities)
        
    def _extract_nationalities(self, candidates: List[str]):
        """
        Filters candidate list to extract nationality terms using the global index.
        """
        if _GLOBAL_INDEX is None:
            print("Error: Index not built. Cannot extract nationalities.")
            return

        nationality_map = _GLOBAL_INDEX.nationalities.nationality_map
        
        found_nationalities = set()
        
        # Check if the candidate matches any known nationality term in the index
        for candidate in candidates:
            if candidate in nationality_map:
                found_nationalities.add(candidate)
                
        self.nationalities = list(found_nationalities)
        
    def _calculate_country_mentions(self):
        """
        Calculates the number of mentions for each country found in the text.
        Stores results in self.country_mentions (OrderedDict).
        """
        if not self.countries:
            return
            
        # Simple counting based on the presence of the country name in the text
        # Note: A more robust implementation would use tokenization and exact matching.
        # Here we iterate over found countries and count occurrences of their names.
        
        text_lower = self.text.lower()
        
        for country_name in self.countries:
            # Use regex word boundaries to count whole word matches
            pattern = re.compile(r'\b' + re.escape(country_name) + r'\b', re.IGNORECASE)
            count = len(pattern.findall(text_lower))
            self.country_mentions[country_name] = count
