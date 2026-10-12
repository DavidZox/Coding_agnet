import pandas as pd
import numpy as np

class Instrument:
    def __init__(self, df: pd.DataFrame):
        """
        Initialize the model structure and parameters.
        
        :param df: The input DataFrame containing financial data.
        """
        self.odf = df.copy()
        self.df = df.copy()
        self._validate_df()

    def _validate_df(self) -> None:
        """
        Validates the DataFrame to ensure it has the required OHLC columns.
        Normalizes column names to lowercase.
        """
        # Normalize column names to lowercase
        self.df.columns = [col.lower() for col in self.df.columns]
        self.odf.columns = [col.lower() for col in self.odf.columns]

        required_columns = ['open', 'high', 'low', 'close']
        for col in required_columns:
            if col not in self.df.columns:
                raise ValueError(f"DataFrame is missing required column: {col}")

class Renko(Instrument):
    def __init__(self, df: pd.DataFrame, brick_size: int = 1, chart_type: int = 0):
        super().__init__(df)
        self.brick_size = brick_size
        self.PERIOD_CLOSE = 1  # Placeholder as per UML/PRD context
        self.PRICE_MOVEMENT = 0
        self.TREND_CHANGE_DIFF = 1
        self.chart_type = chart_type

    def get_ohlc_data(self) -> pd.DataFrame:
        if self.chart_type == self.PERIOD_CLOSE:
            return self.period_close_bricks()
        else:
            self.price_movement_bricks()
            return self.df.copy()

    def price_movement_bricks(self) -> None:
        close_prices = self.df['close'].values
        if len(close_prices) == 0:
            return

        new_rows = []
        current_price = close_prices[0]
        
        for i in range(1, len(close_prices)):
            price = close_prices[i]
            diff = price - current_price
            
            if abs(diff) >= self.brick_size:
                num_bricks = int(abs(diff) // self.brick_size)
                direction = 1 if diff > 0 else -1
                
                for _ in range(num_bricks):
                    prev_price = current_price
                    current_price += (direction * self.brick_size)
                    new_row = {
                        'open': prev_price,
                        'high': max(prev_price, current_price),
                        'low': min(prev_price, current_price),
                        'close': current_price
                    }
                    new_rows.append(new_row)
                    # Update current_price to the new brick's close for the next iteration
        
        if new_rows:
            self.df = pd.DataFrame(new_rows)

    def period_close_bricks(self) -> pd.DataFrame:
        close_prices = self.df['close'].values
        if len(close_prices) == 0:
            return self.df.copy()

        new_rows = []
        current_price = close_prices[0]
        
        for i in range(1, len(close_prices)):
            price = close_prices[i]
            diff = price - current_price
            
            if abs(diff) >= self.brick_size:
                direction = 1 if diff > 0 else -1
                num_bricks = int(abs(diff) // self.brick_size)
                
                for _ in range(num_bricks):
                    prev_price = current_price
                    current_price += (direction * self.brick_size)
                    new_row = {
                        'open': prev_price,
                        'high': max(prev_price, current_price),
                        'low': min(prev_price, current_price),
                        'close': current_price
                    }
                    new_rows.append(new_row)
        
        if new_rows:
            return pd.DataFrame(new_rows)
        return self.df.copy()

    def shift_bricks(self) -> None:
        # Implementation for shifting bricks logic
        # Renko bricks are typically generated based on price movement. 
        # If shift_bricks is intended to align the data, we implement it by 
        # adjusting the DataFrame structure.
        if len(self.df) > 0:
            self.df = self.df.shift(1).dropna()

class LineBreak(Instrument):
    def __init__(self, df: pd.DataFrame, line_number: int = 3):
        super().__init__(df)
        self.line_number = line_number
        self._lines = []

    def uptrend_reversal(self, close: float) -> bool:
        uptrend_lines = [l for l in reversed(self._lines) if l['trend'] == 1]
        if len(uptrend_lines) < self.line_number:
            return False
        threshold = max(l['high'] for l in uptrend_lines[:self.line_number])
        return close > threshold

    def downtrend_reversal(self, close: float) -> bool:
        downtrend_lines = [l for l in reversed(self._lines) if l['trend'] == -1]
        if len(downtrend_lines) < self.line_number:
            return False
        threshold = min(l['low'] for l in downtrend_lines[:self.line_number])
        return close < threshold

    def get_ohlc_data(self) -> pd.DataFrame:
        close_prices = self.df['close'].values
        if len(close_prices) == 0:
            return pd.DataFrame()

        self._lines = []
        first_close = close_prices[0]
        first_open = self.df['open'].values[0]
        initial_trend = 1 if first_close >= first_open else -1
        self._lines.append({
            'open': first_open,
            'high': max(first_open, first_close),
            'low': min(first_open, first_close),
            'close': first_close,
            'trend': initial_trend
        })

        for i in range(1, len(close_prices)):
            price = close_prices[i]
            last_line = self._lines[-1]
            
            if last_line['trend'] == 1:
                if self.downtrend_reversal(price):
                    new_line = {
                        'open': last_line['close'],
                        'high': last_line['close'],
                        'low': min(last_line['close'], price),
                        'close': price,
                        'trend': -1
                    }
                    self._lines.append(new_line)
                elif price > last_line['high']:
                    new_line = {
                        'open': last_line['close'],
                        'high': price,
                        'low': last_line['close'],
                        'close': price,
                        'trend': 1
                    }
                    self._lines.append(new_line)
                else:
                    last_line['low'] = min(last_line['low'], price)
                    last_line['close'] = price
            else:
                if self.uptrend_reversal(price):
                    new_line = {
                        'open': last_line['close'],
                        'high': max(last_line['close'], price),
                        'low': last_line['close'],
                        'close': price,
                        'trend': 1
                    }
                    self._lines.append(new_line)
                elif price < last_line['low']:
                    new_line = {
                        'open': last_line['close'],
                        'high': last_line['close'],
                        'low': price,
                        'close': price,
                        'trend': -1
                    }
                    self._lines.append(new_line)
                else:
                    last_line['high'] = max(last_line['high'], price)
                    last_line['close'] = price

        res_df = pd.DataFrame(self._lines)
        if not res_df.empty:
            res_df['uptrend'] = res_df['trend'] == 1
            return res_df[['open', 'high', 'low', 'close', 'uptrend']]
        return pd.DataFrame()

class PnF(Instrument):
    def __init__(self, df: pd.DataFrame, box_size: int = 1, reversal_size: int = 3):
        super().__init__(df)
        self.box_size = box_size
        self.reversal_size = reversal_size

    @property
    def brick_size(self) -> int:
        return self.box_size

    def get_state(self, uptrend_p1: bool, bricks: int) -> str:
        return 'X' if uptrend_p1 else 'O'

    def roundit(self, x: float, base: int) -> int:
        return int(round(x / base) * base)

    def get_ohlc_data(self, source: str) -> pd.DataFrame:
        # source is expected to be the column name for close prices, e.g., 'close'
        close_prices = self.df[source].values
        if len(close_prices) == 0:
            return pd.DataFrame()

        pnf_data = []
        current_trend = None  # 1 for X (uptrend), -1 for O (downtrend)
        current_price = self.roundit(close_prices[0], self.box_size)
        bricks = 0

        for i in range(1, len(close_prices)):
            price = self.roundit(close_prices[i], self.box_size)
            
            if current_trend is None:
                if price > current_price:
                    current_trend = 1
                    current_price = price
                    bricks = 1
                elif price < current_price:
                    current_trend = -1
                    current_price = price
                    bricks = 1
                else:
                    continue
                
                pnf_data.append({
                    'open': current_price,
                    'high': current_price,
                    'low': current_price,
                    'close': current_price,
                    'trend': current_trend
                })
                continue

            if current_trend == 1:  # Currently in X trend
                if price >= current_price + (self.reversal_size * self.box_size):
                    # Reversal to O
                    current_trend = -1
                    bricks = 1
                    current_price = price
                    pnf_data.append({
                        'open': current_price,
                        'high': current_price,
                        'low': current_price,
                        'close': current_price,
                        'trend': current_trend
                    })
                elif price > current_price:
                    # Continue X
                    diff = price - current_price
                    num_new_bricks = diff // self.box_size
                    if num_new_bricks > 0:
                        new_open = current_price
                        current_price = price
                        bricks += num_new_bricks
                        pnf_data.append({
                            'open': new_open,
                            'high': current_price,
                            'low': new_open,
                            'close': current_price,
                            'trend': current_trend
                        })
                elif price < current_price:
                    # Price dropped but not enough for reversal
                    current_price = price
                    # In PnF, we don't necessarily add a brick for a small drop in X trend
                    # unless it's a reversal. But we update the current price for the next comparison.
                    pass

            elif current_trend == -1:  # Currently in O trend
                if price <= current_price - (self.reversal_size * self.box_size):
                    # Reversal to X
                    current_trend = 1
                    bricks = 1
                    current_price = price
                    pnf_data.append({
                        'open': current_price,
                        'high': current_price,
                        'low': current_price,
                        'close': current_price,
                        'trend': current_trend
                    })
                elif price < current_price:
                    # Continue O
                    diff = current_price - price
                    num_new_bricks = diff // self.box_size
                    if num_new_bricks > 0:
                        new_open = current_price
                        current_price = price
                        bricks += num_new_bricks
                        pnf_data.append({
                            'open': current_price,
                            'high': new_open,
                            'low': current_price,
                            'close': current_price,
                            'trend': current_trend
                        })
                elif price > current_price:
                    current_price = price
                    pass

        res_df = pd.DataFrame(pnf_data)
        if not res_df.empty:
            res_df['uptrend'] = res_df['trend'] == 1
            return res_df[['open', 'high', 'low', 'close', 'uptrend']]
        return pd.DataFrame()

    def get_bar_ohlc_data(self, source: str) -> pd.DataFrame:
        # This is a simplified version that returns the OHLC of the PnF bricks
        # In a real scenario, this might group bricks into bars.
        # For this implementation, we'll return the PnF OHLC data.
        return self.get_ohlc_data(source)
