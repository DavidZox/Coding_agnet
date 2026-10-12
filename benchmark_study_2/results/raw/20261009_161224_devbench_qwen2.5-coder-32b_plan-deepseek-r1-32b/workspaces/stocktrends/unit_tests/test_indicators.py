import pandas as pd
import pytest
from stocktrends.indicators import Instrument, Renko, LineBreak, PnF

# Sample data for testing
data = {
    'date': ['2015/1/1', '2015/1/2', '2015/1/3', '2015/1/4', '2015/1/5'],
    'open': [143.15, 144.00, 145.00, 146.00, 147.00],
    'high': [146.00, 147.00, 148.00, 149.00, 150.00],
    'low': [141.825, 142.00, 143.00, 144.00, 145.00],
    'close': [143.95, 145.00, 146.00, 147.00, 148.00]
}
df = pd.DataFrame(data)

def test_instrument_init():
    instrument = Instrument(df)
    assert instrument.df.equals(df)

def test_renko_init():
    renko = Renko(df)
    assert renko.df.equals(df)

def test_linebreak_init():
    linebreak = LineBreak(df)
    assert linebreak.df.equals(df)

def test_pnf_init():
    pnf = PnF(df)
    assert pnf.df.equals(df)

def test_renko_get_ohlc_data():
    renko = Renko(df, brick_size=1, chart_type='PERIOD_CLOSE')
    ohlc_data = renko.get_ohlc_data()
    assert not ohlc_data.empty
    assert 'date' in ohlc_data.columns
    assert 'open' in ohlc_data.columns
    assert 'high' in ohlc_data.columns
    assert 'low' in ohlc_data.columns
    assert 'close' in ohlc_data.columns
    assert len(ohlc_data) > 0

def test_linebreak_get_ohlc_data():
    linebreak = LineBreak(df, line_number=3)
    ohlc_data = linebreak.get_ohlc_data()
    assert not ohlc_data.empty
    assert 'date' in ohlc_data.columns
    assert 'open' in ohlc_data.columns
    assert 'high' in ohlc_data.columns
    assert 'low' in ohlc_data.columns
    assert 'close' in ohlc_data.columns
    assert len(ohlc_data) > 0

def test_pnf_get_ohlc_data():
    pnf = PnF(df, box_size=1, reversal_size=3)
    ohlc_data = pnf.get_ohlc_data()
    assert not ohlc_data.empty
    assert 'date' in ohlc_data.columns
    assert 'open' in ohlc_data.columns
    assert 'high' in ohlc_data.columns
    assert 'low' in ohlc_data.columns
    assert 'close' in ohlc_data.columns
    assert len(ohlc_data) > 0

def test_renko_period_close_bricks():
    renko = Renko(df, brick_size=1, chart_type='PERIOD_CLOSE')
    bricks = renko.period_close_bricks()
    assert not bricks.empty
    assert 'date' in bricks.columns
    assert 'open' in bricks.columns
    assert 'high' in bricks.columns
    assert 'low' in bricks.columns
    assert 'close' in bricks.columns
    assert len(bricks) > 0

def test_renko_price_movement_bricks():
    renko = Renko(df, brick_size=1, chart_type='PRICE_MOVEMENT')
    bricks = renko.price_movement_bricks()
    assert not bricks.empty
    assert 'date' in bricks.columns
    assert 'open' in bricks.columns
    assert 'high' in bricks.columns
    assert 'low' in bricks.columns
    assert 'close' in bricks.columns
    assert len(bricks) > 0

def test_linebreak_uptrend_reversal():
    linebreak = LineBreak(df, line_number=3)
    assert not linebreak.uptrend_reversal(143.95)

def test_linebreak_downtrend_reversal():
    linebreak = LineBreak(df, line_number=3)
    assert not linebreak.downtrend_reversal(143.95)

def test_pnf_get_state():
    pnf = PnF(df, box_size=1, reversal_size=3)
    state = pnf.get_state(True, 1)
    assert state in ['X', 'O']

def test_pnf_roundit():
    pnf = PnF(df, box_size=1, reversal_size=3)
    rounded_value = pnf.roundit(143.95, 1)
    assert rounded_value == 144
