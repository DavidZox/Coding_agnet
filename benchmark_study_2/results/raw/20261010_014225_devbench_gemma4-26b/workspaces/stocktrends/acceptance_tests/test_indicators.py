import pytest
import pandas as pd
import numpy as np
from stocktrends.indicators import Renko, LineBreak

def test_renko_indicator():
    # Load acceptance sample for Renko
    df = pd.read_csv('acceptance_samples/HOOLI.csv')
    # Normalize column names to lowercase as per PRD
    df.columns = [col.lower() for col in df.columns]
    
    # The sample hooli_renko_4.csv implies brick_size=4
    # Based on the PRD, we need to compare closing prices
    renko = Renko(df)
    renko.brick_size = 4
    renko.chart_type = 'PERIOD_CLOSE' # Assuming PERIOD_CLOSE based on UML/PRD
    
    renko_df = renko.get_ohlc_data()
    
    # Load expected values
    expected_df = pd.read_csv('acceptance_samples/hooli_renko_4.csv')
    expected_df.columns = [col.lower() for col in expected_df.columns]
    
    # The acceptance criteria: absolute difference <= 1e-12
    # We compare the 'close' column
    assert len(renko_df) == len(expected_df), f"Expected length {len(expected_df)}, got {len(renko_df)}"
    
    for i in range(len(expected_df)):
        actual_close = renko_df.iloc[i]['close']
        expected_close = expected_df.iloc[i]['close']
        assert abs(actual_close - expected_close) <= 1e-12, \
            f"At index {i}, expected {expected_close}, got {actual_close}"

def test_linebreak_indicator():
    # Load acceptance sample for Line Break
    df = pd.read_csv('acceptance_samples/HOOLI.csv')
    df.columns = [col.lower() for col in df.columns]
    
    # The sample hooli_linebreak_3.csv implies line_number=3
    linebreak = LineBreak(df)
    linebreak.line_number = 3
    
    lb_df = linebreak.get_ohlc_data()
    
    # Load expected values
    expected_df = pd.read_csv('acceptance_samples/hooli_linebreak_3.csv')
    expected_df.columns = [col.lower() for col in expected_df.columns]
    
    # The acceptance criteria: absolute difference <= 1e-12
    assert len(lb_df) == len(expected_df), f"Expected length {len(expected_df)}, got {len(lb_df)}"
    
    for i in range(len(expected_df)):
        actual_close = lb_df.iloc[i]['close']
        expected_close = expected_df.iloc[i]['close']
        assert abs(actual_close - expected_close) <= 1e-12, \
            f"At index {i}, expected {expected_close}, got {actual_close}"

def test_data_integrity():
    # Basic check to ensure data shapes are handled correctly as per PRD
    df = pd.read_csv('acceptance_samples/HOOLI.csv')
    df.columns = [col.lower() for col in df.columns]
    
    renko = Renko(df)
    renko.brick_size = 4
    renko_df = renko.get_ohlc_data()
    
    assert not renko_df.empty
    assert all(col in renko_df.columns for col in ['open', 'high', 'low', 'close'])
