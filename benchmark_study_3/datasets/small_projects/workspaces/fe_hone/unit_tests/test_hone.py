import os
import unittest
from hone import hone
from hone.utils import test_utils

dirname = os.path.dirname(os.path.dirname(__file__))
csv_A_path = os.path.join(dirname, "data_file", "small_cats_dataset", "dataset.csv")
json_A_path = os.path.join(dirname, "data_file", "small_cats_dataset", "nested_dataset.json")
json_schema_A_path = os.path.join(dirname, "data_file", "small_cats_dataset", "nested_schema.json")
csv_B_path = os.path.join(dirname, "data_file", "comma_test", "dataset.csv")
json_B_path = os.path.join(dirname, "data_file", "comma_test", "nested_dataset.json")
csv_C_path = os.path.join(dirname, "data_file", "quotes_test", "dataset.csv")
json_C_path = os.path.join(dirname, "data_file", "quotes_test", "nested_dataset.json")



if __name__ == '__main__':
    unittest.main()
