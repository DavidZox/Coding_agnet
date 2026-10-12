import pandas as pd
import numpy as np
from stocktrends.indicators import PnF

def test_pnf_logic():
    # Create dummy data
    data = {
        'date': ['2021/6/8', '2021/6/9', '2021/6/10', '2021/6/11', '2021/6/12'],
        'open': [100.0, 105.0, 110.0, 105.0, 100.0],
        'high': [110.0, 115.0, 115.0, 110.0, 105.0],
        'low': [95.0, 100.0, 105.0, 100.0, 95.0],
        'close': [105.0, 110.0, 105.0, 100.0, 100.0]
    }
    df = pd.DataFrame(data)
    
    # Initialize PnF
    # box_size: size of each brick
    # reversal_size: number of bricks for reversal
    box_size = 5
    reversal_size = 3
    pnf = PnF(df, box_size, reversal_size)

    print("Testing roundit...")
    # Test roundit: should round to nearest multiple of base
    assert pnf.roundit(12.3, 5) == 10
    assert pnf.roundit(12.7, 5) == 15
    assert pnf.roundit(7.5, 5) == 10
    assert pnf.roundit(2.5, 5) == 5
    print("roundit tests passed!")

    print("Testing brick_size...")
    assert pnf.brick_size == box_size
    print("brick_size tests passed!")

    print("Testing get_state...")
    # get_state(uptrend_p1, bricks)
    # If uptrend_p1 is True, and bricks > 0, state should be 'X' (uptrend)
    # If uptrend_p1 is False, and bricks > 0, state should be 'O' (downtrend)
    assert pnf.get_state(True, 2) == 'X'
    assert pnf.get_state(False, 2) == 'O'
    assert pnf.get_state(True, 0) == 'X' # Based on logic, if no bricks, it stays in current trend or starts
    print("get_state tests passed!")

    print("Testing get_ohlc_data...")
    # This tests the full PnF logic and output format
    try:
        ohlc_df = pnf.get_ohlc_data(source='close')
        print("get_ohlc_data output:")
        print(ohlc_df)
        
        # Check if columns are correct (should be date, open, high, low, close)
        # Note: The actual columns depend on implementation, but usually include OHLC
        assert not ohlc_df.empty
        assert 'close' in ohlc_df.columns
        print("get_ohlc_data tests passed!")
    except Exception as e:
        print(f"get_ohlc_data failed with error: {e}")
        raise e

    print("Testing get_bar_ohlc_data...")
    try:
        bar_ohlc = pnf.get_bar_ohlc_data(source='close')
        print("get_bar_ohlc_data output:")
        print(bar_ohlc)
        assert not bar_ohlc.empty
        print("get_bar_ohlc_data tests passed!")
    except Exception as e:
        print(f"get_bar_ohlc_data failed with error: {e}")
        raise e

    print("\nAll PnF logic tests passed successfully!")

if __name__ == "__main__":
    test_pnf_logic()
