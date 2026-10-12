import sys
import os
import pandas as pd

# Add the parent directory to the system path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from stocktrends.indicators import Instrument, Renko, LineBreak, PnF

def main():
    # Load sample data
    df = pd.read_csv('unit_samples/HOOLI.csv')
    
    # Initialize Instrument
    instrument = Instrument(df)
    
    # Initialize Renko Indicator
    renko = Renko(instrument.df)
    renko.chart_type = renko.PERIOD_CLOSE
    renko.brick_size = 4
    renko_df = renko.get_ohlc_data()
    print("Renko Indicator Data:")
    print(renko_df.head())
    
    # Initialize Line Break Indicator
    line_break = LineBreak(instrument.df)
    line_break.line_number = 3
    line_break_df = line_break.get_ohlc_data()
    print("\nLine Break Indicator Data:")
    print(line_break_df.head())
    
    # Initialize PnF Indicator
    pnf = PnF(instrument.df)
    pnf.box_size = 4
    pnf.reversal_size = 2
    pnf_df = pnf.get_ohlc_data(source='close')
    print("\nPnF Indicator Data:")
    print(pnf_df.head())

if __name__ == "__main__":
    main()
