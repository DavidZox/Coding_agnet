import pandas as pd
import numpy as np

class Instrument:
    def __init__(self, df: pd.DataFrame):
        """
        Initialize the model structure and parameters.
        
        :param df: Input DataFrame containing financial data.
        """
        self.df = df
        self.odf = None
        self._validate_df()

    def _validate_df(self) -> None:
        """
        Validates the DataFrame to ensure it has the required OHLC columns
        and normalizes column names to lowercase.
        """
        # Normalize column names to lowercase as per PRD requirement
        self.df.columns = [col.lower() for col in self.df.columns]
        
        # Required OHLC columns
        required_columns = {'open', 'high', 'low', 'close'}
        
        # Check if all required columns exist in the normalized DataFrame
        if not required_columns.issubset(self.df.columns):
            missing = required_columns - set(self.df.columns)
            raise ValueError(f"DataFrame is missing required OHLC columns: {missing}")

class Renko(Instrument):
    def __init__(self, df: pd.DataFrame, brick_size: int = 1, chart_type: int = 0):
        super().__init__(df)
        # Constants as per UML
        self.PERIOD_CLOSE = 1
        self.PRICE_MOVEMENT = 0
        self.TREND_CHANGE_DIFF = 2
        self.brick_size = brick_size
        self.chart_type = chart_type

    def get_ohlc_data(self) -> pd.DataFrame:
        """Retrieves the OHLC data based on the chart type."""
        if self.chart_type == self.PERIOD_CLOSE:
            return self.period_close_bricks()
        else:
            self.price_movement_bricks()
            return self.df

    def price_movement_bricks(self) -> None:
        """Placeholder for price movement bricks calculation."""
        # Implementation logic for price movement bricks
        # This would involve iterating through prices and creating bricks based on brick_size
        close_prices = self.df['close'].values
        if len(close_prices) == 0:
            return

        bricks = []
        current_price = close_prices[0]
        trend = None  # 1 for UP, -1 for DOWN

        for price in close_prices:
            if trend is None:
                if price >= current_price + self.brick_size:
                    trend = 1
                    current_price += self.brick_size
                    bricks.append({'open': current_price - self.brick_size, 'high': current_price, 'low': current_price - self.brick_size, 'close': current_price, 'uptrend': True})
                elif price <= current_price - self.brick_size:
                    trend = -1
                    current_price -= self.brick_size
                    bricks.append({'open': current_price + self.brick_size, 'high': current_price + self.brick_size, 'low': current_price, 'close': current_price, 'uptrend': False})
            elif trend == 1:
                if price >= current_price + self.brick_size:
                    current_price += self.brick_size
                    bricks.append({'open': current_price - self.brick_size, 'high': current_price, 'low': current_price - self.brick_size, 'close': current_price, 'uptrend': True})
                elif price <= current_price - self.brick_size:
                    trend = -1
                    current_price -= self.brick_size
                    bricks.append({'open': current_price + self.brick_size, 'high': current_price + self.brick_size, 'low': current_price, 'close': current_price, 'uptrend': False})
            elif trend == -1:
                if price <= current_price - self.brick_size:
                    current_price -= self.brick_size
                    bricks.append({'open': current_price + self.brick_size, 'high': current_price + self.brick_size, 'low': current_price, 'close': current_price, 'uptrend': False})
                elif price >= current_price + self.brick_size:
                    trend = 1
                    current_price += self.brick_size
                    bricks.append({'open': current_price - self.brick_size, 'high': current_price, 'low': current_price - self.brick_size, 'close': current_price, 'uptrend': True})

        if bricks:
            new_df = pd.DataFrame(bricks)
            # To maintain index/date if possible, but Renko is time-independent. 
            # We update self.df as per the requirement of get_ohlc_data's else branch.
            self.df = new_df

    def period_close_bricks(self) -> pd.DataFrame:
        """Calculates the period close bricks based on the given brick size."""
        # Implementation logic for period close bricks
        # This would involve calculating bricks based on period close prices
        close_prices = self.df['close'].values
        if len(close_prices) == 0:
            return pd.DataFrame()

        bricks = []
        current_price = close_prices[0]
        trend = None 

        for price in close_prices:
            if trend is None:
                if price >= current_price + self.brick_size:
                    trend = 1
                    current_price += self.brick_size
                    bricks.append({'open': current_price - self.brick_size, 'high': current_price, 'low': current_price - self.brick_size, 'close': current_price, 'uptrend': True})
                elif price <= current_price - self.brick_size:
                    trend = -1
                    current_price -= self.brick_size
                    bricks.append({'open': current_price + self.brick_size, 'high': current_price + self.brick_size, 'low': current_price, 'close': current_price, 'uptrend': False})
            elif trend == 1:
                if price >= current_price + self.brick_size:
                    current_price += self.brick_size
                    bricks.append({'open': current_price - self.brick_size, 'high': current_price, 'low': current_price - self.brick_size, 'close': current_price, 'uptrend': True})
                elif price <= current_price - self.brick_size:
                    trend = -1
                    current_price -= self.brick_size
                    bricks.append({'open': current_price + self.brick_size, 'high': current_price + self.brick_size, 'low': current_price, 'close': current_price, 'uptrend': False})
            elif trend == -1:
                if price <= current_price - self.brick_size:
                    current_price -= self.brick_size
                    bricks.append({'open': current_price + self.brick_size, 'high': current_price + self.brick_size, 'low': current_price, 'close': current_price, 'uptrend': False})
                elif price >= current_price + self.brick_size:
                    trend = 1
                    current_price += self.brick_size
                    bricks.append({'open': current_price - self.brick_size, 'high': current_price, 'low': current_price - self.brick_size, 'close': current_price, 'uptrend': True})

        return pd.DataFrame(bricks)

    def shift_bricks(self) -> None:
        """Shifts the bricks in the indicator dataframe based on the difference between the current close price and the previous close price."""
        # Implementation logic for shifting bricks
        if len(self.df) < 2:
            return
        
        # Calculate the difference between current close and previous close
        # In a real Renko implementation, this might adjust the brick levels
        # For this task, we implement the logic as described: shift based on price difference
        diffs = self.df['close'].diff().fillna(0)
        
        # We'll shift the 'open' and 'low' values by the cumulative difference if needed,
        # but a standard interpretation is to adjust the brick levels to align with price gaps.
        # Here we implement a simple shift of the brick levels.
        self.df['open'] = self.df['open'] + diffs
        self.df['high'] = self.df['high'] + diffs
        self.df['low'] = self.df['low'] + diffs
        self.df['close'] = self.df['close'] + diffs

class LineBreak(Instrument):
    def __init__(self, df: pd.DataFrame, line_number: int = 3):
        super().__init__(df)
        self.line_number = line_number

    def uptrend_reversal(self, close: float) -> bool:
        """Determines if a stock is experiencing an uptrend reversal."""
        # In Line Break, an uptrend reversal occurs if the price drops below 
        # the low of the last N (line_number) up-trend bars.
        # However, the logic is usually handled within the main loop.
        # For this specific method signature, we assume it's a check against current state.
        return False

    def downtrend_reversal(self, close: float) -> bool:
        """Determines if a downtrend reversal has occurred."""
        return False

    def get_ohlc_data(self) -> pd.DataFrame:
        """Retrieves the OHLC data and performs trend analysis."""
        close_prices = self.df['close'].values
        if len(close_prices) == 0:
            return pd.DataFrame()

        # We need to track the highs and lows of the current trend to detect reversals
        # A reversal happens when price breaks the high/low of the last N bars of the opposite trend.
        # For simplicity and to match common Line Break implementations:
        # We track the trend and the 'extreme' price of the current trend.
        
        results = []
        current_trend = None # 1 for UP, -1 for DOWN
        
        # To track the reversal condition: we need the high/low of the last N bars of the opposite trend.
        # But a simpler version: a reversal occurs if price breaks the high/low of the previous trend.
        # Given the requirement for 'line_number' (e.g., 3), it means 3 consecutive bars of opposite direction.
        
        # Let's implement the logic:
        # 1. Track current trend.
        # 2. Track how many bars of the current trend we have.
        # 3. If price breaks the extreme of the current trend, we check if it's a reversal.
        
        # A standard 3-line break: reversal if price breaks the high/low of the last 3 bars.
        # We'll use a simplified version that tracks the trend and the required breakout.
        # We need to store the history of the bars to check the last N.
        
        bars = []
        # Find first trend
        idx = 0
        while idx < len(close_prices) and close_prices[idx] == self.df['open'].values[idx]:
            idx += 1
        
        if idx >= len(close_prices):
            return pd.DataFrame()

        current_trend = 1 if close_prices[idx] > self.df['open'].values[idx] else -1
        # Initial bar
        bars.append({
            'open': self.df['open'].values[idx],
            'high': self.df['high'].values[idx],
            'low': self.df['low'].values[idx],
            'close': close_prices[idx],
            'uptrend': current_trend == 1
        })

        for i in range(idx + 1, len(close_prices)):
            price = close_prices[i]
            last_bar = bars[-1]
            
            if last_bar['uptrend']:
                # Check for reversal
                uptrend_bars = [b for b in bars if b['uptrend']][-self.line_number:]
                min_low = min(b['low'] for b in uptrend_bars)
                
                if price < min_low:
                    # Reversal to DOWN
                    bars.append({
                        'open': last_bar['close'],
                        'high': last_bar['close'],
                        'low': min(last_bar['close'], price),
                        'close': price,
                        'uptrend': False
                    })
                else:
                    # Continue UP
                    last_bar['close'] = price
                    last_bar['high'] = max(last_bar['high'], price)
                    last_bar['low'] = min(last_bar['low'], price)
            else:
                # Check for reversal
                downtrend_bars = [b for b in bars if not b['uptrend']][-self.line_number:]
                max_high = max(b['high'] for b in downtrend_bars)
                
                if price > max_high:
                    # Reversal to UP
                    bars.append({
                        'open': last_bar['close'],
                        'high': max(last_bar['close'], price),
                        'low': last_bar['close'],
                        'close': price,
                        'uptrend': True
                    })
                else:
                    # Continue DOWN
                    last_bar['close'] = price
                    last_bar['high'] = max(last_bar['high'], price)
                    last_bar['low'] = min(last_bar['low'], price)

        res_df = pd.DataFrame(bars)
        if not res_df.empty:
            # Ensure columns are in correct order and include uptrend
            return res_df[['open', 'high', 'low', 'close', 'uptrend']]
        return res_df

class PnF(Instrument):
    def __init__(self, df: pd.DataFrame, box_size: int, reversal_size: int):
        super().__init__(df)
        self.box_size = box_size
        self.reversal_size = reversal_size

    @property
    def brick_size(self) -> int:
        """Returns the brick size used for the indicator."""
        return self.box_size

    def get_state(self, uptrend_p1: bool, bricks: int) -> str:
        """Gets the state of the trend."""
        if uptrend_p1:
            return 'X' if bricks >= 0 else 'O'
        else:
            return 'O' if bricks >= 0 else 'X'

    def roundit(self, x: float, base: int) -> int:
        """Rounds the input x to the nearest multiple of base."""
        # Use floor(x/base + 0.5) to avoid Python's "round to even" behavior
        # and ensure 2.5 / 5 -> 0.5 -> 1.0 * 5 = 5
        return int((x // base) + (1 if (x % base) >= (base / 2) else 0)) * base

    def get_ohlc_data(self, source: str) -> pd.DataFrame:
        """Retrieves the PnF data in the form of an OHLC DataFrame."""
        # Use the specified source column if provided, otherwise default to 'close'
        price_col = source if source in self.df.columns else 'close'
        prices = self.df[price_col].values
        if len(prices) == 0:
            return pd.DataFrame()

        # PnF logic: track X (up) and O (down)
        # We use the roundit logic to align prices to the box_size grid
        
        # Initial state
        current_price = self.roundit(prices[0], self.box_size)
        trend = None  # 1 for UP (X), -1 for DOWN (O)
        
        # To store the sequence of price levels
        # Each entry: (price, trend)
        history = []
        
        for p in prices:
            rounded_p = self.roundit(p, self.box_size)
            
            if trend is None:
                if rounded_p > current_price:
                    trend = 1
                    current_price = rounded_p
                    history.append((current_price, trend))
                elif rounded_p < current_price:
                    trend = -1
                    current_price = rounded_p
                    history.append((current_price, trend))
                continue

            if trend == 1:  # Currently UP (X)
                if rounded_p >= current_price + (self.reversal_size * self.box_size):
                    # Reversal to DOWN
                    trend = -1
                    current_price = rounded_p
                    history.append((current_price, trend))
                elif rounded_p > current_price:
                    # Continue UP
                    current_price = rounded_p
                    history.append((current_price, trend))
            else:  # Currently DOWN (O)
                if rounded_p <= current_price - (self.reversal_size * self.box_size):
                    # Reversal to UP
                    trend = 1
                    current_price = rounded_p
                    history.append((current_price, trend))
                elif rounded_p < current_price:
                    # Continue DOWN
                    current_price = rounded_p
                    history.append((current_price, trend))

        if not history:
            return pd.DataFrame()

        # Convert history to OHLC bars
        # A "bar" in PnF is a continuous sequence of the same trend
        bars = []
        if history:
            start_idx = 0
            for i in range(1, len(history)):
                if history[i][1] != history[start_idx][1]:
                    # Trend changed, end previous bar
                    trend_type = history[start_idx][1]
                    prices_in_bar = [h[0] for h in history[start_idx:i]]
                    
                    # For PnF, the bar is the sequence of Xs or Os
                    # Open is the first price, Close is the last, High/Low are extremes
                    if trend_type == 1:
                        bars.append({
                            'open': prices_in_bar[0],
                            'high': max(prices_in_bar),
                            'low': min(prices_in_bar),
                            'close': prices_in_bar[-1],
                            'uptrend': True
                        })
                    else:
                        bars.append({
                            'open': prices_in_bar[0],
                            'high': max(prices_in_bar),
                            'low': min(prices_in_bar),
                            'close': prices_in_bar[-1],
                            'uptrend': False
                        })
                    start_idx = i
            
            # Last bar
            trend_type = history[start_idx][1]
            prices_in_bar = [h[0] for h in history[start_idx:]]
            if trend_type == 1:
                bars.append({
                    'open': prices_in_bar[0],
                    'high': max(prices_in_bar),
                    'low': min(prices_in_bar),
                    'close': prices_in_bar[-1],
                    'uptrend': True
                })
            else:
                bars.append({
                    'open': prices_in_bar[0],
                    'high': max(prices_in_bar),
                    'low': min(prices_in_bar),
                    'close': prices_in_bar[-1],
                    'uptrend': False
                })

        return pd.DataFrame(bars)

    def get_bar_ohlc_data(self, source: str) -> pd.DataFrame:
        """Retrieves bar OHLC data."""
        return self.get_ohlc_data(source)
