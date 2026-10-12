import os
import csv
from collections import OrderedDict, namedtuple
from typing import List, Dict, Any, Optional
import re # Import re for regex operations

# Define the structure for the index as required by the design
# Index structure: (nationalities_map, countries_map, cities_map)
GeoIndex = namedtuple('GeoIndex', ['nationalities_map', 'countries_map', 'cities_map'])

# Assuming the project root is the current working directory for path resolution
# In a real package structure, this might need more robust path handling.

def get_data_path(path: str) -> str:
    """
    A utility function to construct a file path by joining the root directory 
    with a given path, specifically used to access data files.
    
    Args:
        path: The relative path to the data file within the geotext/data_file directory.
        
    Returns:
        The complete, absolute path to the data file.
    """
    # Construct the path relative to the project root, assuming execution context allows this.
    # Since the structure is geotext/data_file, we join these components.
    return os.path.join("geotext", "data_file", path)

def read_table(filename: str, usecols: List[int], sep: str = '\t', comment: str = '#', encoding: str = 'utf-8', skip: int = 0) -> Dict[Any, Dict[int, Any]]:
    """
    Parses data files from the data_file directory to create dictionaries 
    mapping terms to their corresponding values based on the specified columns.

    Args:
        filename: The name of the data file (e.g., 'cities15000.txt').
        usecols: A list of 0-based column indices to use as keys and values.
        sep: The delimiter used in the file.
        comment: Lines starting with this string are ignored.
        encoding: The file encoding.
        skip: Number of initial lines to skip (e.g., header lines).

    Returns:
        A dictionary where keys are the values from the first specified column, 
        and values are dictionaries mapping column indices to their data.
    """
    full_path = get_data_path(filename)
    
    data_map: Dict[Any, Dict[int, Any]] = {}
    
    try:
        with open(full_path, 'r', encoding=encoding) as f:
            # Skip initial lines
            for _ in range(skip):
                next(f)
            
            # Read lines and process
            for line in f:
                line = line.strip()
                if not line or line.startswith(comment):
                    continue
                
                # Split the line based on the specified separator
                parts = line.split(sep)
                
                if not parts:
                    continue

                # The key is the value from the first specified column
                try:
                    key_index = usecols[0]
                    key_value = parts[key_index].strip()
                except IndexError:
                    # Skip line if it doesn't have enough columns for the key
                    continue
                
                if key_value not in data_map:
                    data_map[key_value] = {}
                
                # Store all specified columns for this key
                for col_index in usecols:
                    if col_index < len(parts):
                        data_map[key_value][col_index] = parts[col_index].strip()
                        
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
    of nationalities, cities, and countries in the form of a namedtuple.

    Returns:
        GeoIndex: A namedtuple containing maps for nationalities, countries, and cities.
    """
    # 1. Load Nationalities (nationalities.txt: format 'afghan:AF')
    # We use the nationality name as the key and the code as the value.
    nationalities_data = read_table(
        filename='nationalities.txt', 
        usecols=[0, 1], 
        sep=':', 
        comment='#', 
        encoding='utf-8'
    )
    nationalities_map = {}
    for name, data in nationalities_data.items():
        # Assuming the structure from read_table results in data[1] being the code if sep=':'
        if 1 in data:
            nationalities_map[name] = data[1]


    # 2. Load Country Info (countryInfo.txt: format 'AD	AND	020	AN	Andorra...')
    # We map ISO code (Col 0) to Country Name (Col 1) and ISO3 (Col 2) to Country Name.
    # For simplicity, we map ISO code to Country Name.
    country_info_data = read_table(
        filename='countryInfo.txt', 
        usecols=[0, 1, 2], 
        sep='\t', 
        comment='#', 
        encoding='utf-8'
    )
    countries_map = {}
    for iso_code, data in country_info_data.items():
        # Map ISO code (key) to Country Name (Col 1)
        if 1 in data:
            countries_map[iso_code] = data[1]
        # Also map ISO3 (Col 2) to Country Name for potential lookups
        if 2 in data:
            iso3 = data[2]
            if iso3:
                countries_map[iso3] = data.get(1, '')


    # 3. Load Cities Data (cities15000.txt: format '2081986	Palikir - National Government Center	Palikir - National Government Center	...	PPLC	FM		02	SO')
    # We map City Name (Col 1) to Country Code (Col 7, assuming it's the country code field based on structure)
    # Note: The structure of cities15000.txt is complex. Based on the example, we assume the country code is in a specific column.
    # Let's assume the country code is in column 7 (0-indexed) based on typical GeoNames data structure, 
    # although the example provided is ambiguous regarding the exact country code column.
    # We will use the structure implied by the PRD: City -> Country Code mapping.
    cities_data = read_table(
        filename='cities15000.txt', 
        usecols=[1, 7], # City Name (Col 1), Country Code (Col 7)
        sep='\t', 
        comment='#', 
        encoding='utf-8'
    )
    cities_map = {}
    for city_name, data in cities_data.items():
        # Map City Name (key) to Country Code (Col 7)
        if 7 in data:
            country_code = data[7]
            cities_map[city_name] = country_code
        
    return GeoIndex(
        nationalities_map=nationalities_map, 
        countries_map=countries_map, 
        cities_map=cities_map
    )


class GeoText:
    """
    A class that extracts cities and countries from a given text.
    """
    def __init__(self, text: str, country: Optional[str] = None):
        """
        Initializes the GeoText object.
        
        Args:
            text: The input text to analyze.
            country: Optional country code to filter cities by.
        """
        self.text: str = text
        self.country: Optional[str] = country
        self.countries: List[str] = []
        self.cities: List[str] = []
        self.nationalities: List[str] = []
        self.country_mentions: OrderedDict[str, int] = OrderedDict()
        # Regex to find sequences of words/names, capturing potential candidates
        self._city_regex: re.Pattern = re.compile(r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)")
        
        # Load the index upon initialization, as per UML sequence diagram flow
        self.index: GeoIndex = build_index() 
        
        # Initialize internal state for extraction process
        self._candidates: List[str] = []

    def _find_candidates(self, text: str) -> List[str]:
        """
        Finds potential place names in the text using regex.
        
        Args:
            text: The input text.
            
        Returns:
            A list of potential candidate strings.
        """
        # Find all matches based on the defined regex pattern
        matches = self._city_regex.findall(text)
        # Return unique matches
        return list(set(matches))

    def _extract_countries(self, candidates: List[str]) -> None:
        """
        Extracts country names from candidates by matching against the countries_map values.
        """
        country_names_in_index = set(self.index.countries_map.values())
        
        for candidate in candidates:
            # Check if the candidate matches any known country name
            if candidate in country_names_in_index:
                self.countries.append(candidate)
                # Update mentions count
                self.country_mentions[candidate] = self.country_mentions.get(candidate, 0) + 1

    def _extract_cities(self, candidates: List[str], country_filter: Optional[str]) -> None:
        """
        Extracts city names from candidates, optionally filtering by country code.
        """
        for candidate in candidates:
            # Check if the candidate exists in the cities_map
            if candidate in self.index.cities_map:
                country_code = self.index.cities_map[candidate]
                
                # Apply country filter if provided
                if country_filter is None or country_code == country_filter:
                    self.cities.append(candidate)

    def _extract_nationalities(self, candidates: List[str]) -> None:
        """
        Extracts nationality terms from candidates by matching against nationalities_map keys.
        """
        nationality_names_in_index = set(self.index.nationalities_map.keys())
        
        for candidate in candidates:
            # Check if the candidate matches any known nationality name
            if candidate in nationality_names_in_index:
                self.nationalities.append(candidate)

    def _calculate_country_mentions(self) -> None:
        """
        Calculates the count of mentions for each country found by counting occurrences 
        of identified country names in the original text.
        """
        # Reset mentions count before recalculating
        self.country_mentions = OrderedDict()
        
        # Iterate over all unique countries found
        for country_name in set(self.countries):
            # Count occurrences of the country name in the original text (case-insensitive)
            count = self.text.lower().count(country_name.lower())
            self.country_mentions[country_name] = count
