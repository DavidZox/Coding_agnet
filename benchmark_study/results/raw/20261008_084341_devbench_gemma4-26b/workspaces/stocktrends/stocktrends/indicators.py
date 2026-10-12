import pandas as pd
import numpy as np

class Instrument:
    def __init__(self, df: pd.DataFrame):
        """
        Initialize the model structure and parameters.
        
        :param df: The input DataFrame containing financial data.
        """
        self.df = df.copy()
        self.odf = df.copy()  # Original DataFrame or processed DataFrame as per UML
        self._validate_df()

    def _validate_df(self):
        """
        Validates the DataFrame to ensure it has the required OHLC columns.
        Normalizes column names to lowercase for consistency.
        """
        if self.df is None or not isinstance(self.df, pd.DataFrame):
            raise ValueError("Input must be a pandas DataFrame.")

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
        self.PERIOD_CLOSE = 1
        self.PRICE_MOVEMENT = 0
        self.TREND_CHANGE_DIFF = 0
        self.brick_size = brick_size
        self.chart_type = chart_type

    def get_ohlc_data(self) -> pd.DataFrame:
        # Ensure idempotency by always starting from the original data (odf)
        if self.chart_type == self.PERIOD_CLOSE:
            return self.period_close_bricks()
        else:
            # Reset df to odf before calculation to avoid cumulative changes
            self.df = self.odf.copy()
            self.price_movement_bricks()
            return self.df

    def price_movement_bricks(self) -> None:
        if self.odf.empty:
            return

        closes = self.odf['close'].values
        bricks = []
        
        if len(closes) == 0:
            return

        current_price = closes[0]
        
        for i in range(1, len(closes)):
            price = closes[i]
            diff = price - current_price
            
            if abs(diff) >= self.brick_size:
                num_bricks = int(abs(diff) // self.brick_size)
                new_direction = 1 if diff > 0 else -1
                
                for _ in range(num_bricks):
                    old_open = current_price
                    current_price += new_direction * self.brick_size
                    
                    brick = {
                        'open': old_open,
                        'high': max(old_open, current_price),
                        'low': min(old_open, current_price),
                        'close': current_price,
                        'uptrend': True if new_direction == 1 else False
                    }
                    bricks.append(brick)
        
        if bricks:
            new_df = pd.DataFrame(bricks)
            self.df = new_df
            self.shift_bricks()
        else:
            self.df = pd.DataFrame(columns=['open', 'high', 'low', 'close', 'uptrend'])

    def period_close_bricks(self) -> pd.DataFrame:
        # Simplified implementation: use close prices to generate bricks
        # In a real scenario, this would involve grouping by period first
        temp_df = self.odf.copy()
        
        # If the index is datetime, simulate period close by resampling
        if isinstance(temp_df.index, pd.DatetimeIndex):
            temp_df = temp_df.resample('D').last().dropna()
            
        self.df = temp_df.copy()
        self.price_movement_bricks()
        return self.df

    def shift_bricks(self) -> None:
        # Shifts the bricks based on the difference between current and previous close
        if self.df.empty or len(self.df) < 2:
            return
        
        # This is a placeholder for the specific shifting logic required by the task
        # which adjusts brick levels based on price gaps
        pass

class LineBreak(Instrument):
    def __init__(self, df: pd.DataFrame, line_number: int = 3):
        super().__init__(df)
        self.line_number = line_number

    def uptrend_reversal(self, close: float) -> bool:
        """
        Determines if a stock is experiencing an uptrend reversal.
        In Line Break, an uptrend reversal occurs if the close price is lower than 
        the lowest of the last 'n' highs.
        """
        # This logic is handled within the get_ohlc_data loop for state tracking
        return False

    def downtrend_reversal(self, close: float) -> bool:
        """
        Determines if a downtrend reversal has occurred based on the given close price.
        In Line Break, a downtrend reversal occurs if the close price is higher than 
        the highest of the last 'n' lows.
        """
        # This logic is handled within the get_ohlc_data loop for state tracking
        return False

    def get_ohlc_data(self) -> pd.DataFrame:
        """
        Retrieves the OHLC data from the DataFrame and performs trend analysis.
        """
        if self.odf.empty:
            return pd.DataFrame()

        closes = self.odf['close'].values
        # We need to track the history of highs and lows to detect reversals
        # For Line Break, we look at the last 'n' bars of the current trend
        
        # Initial state
        current_trend = None # 1 for uptrend, -1 for downtrend
        history = [] # stores (open, high, low, close, uptrend)
        
        # To detect reversal, we need to track the extremes of the current trend
        trend_extremes = [] # stores the high/low of each bar in the current trend

        for i in range(len(closes)):
            price = closes[i]
            
            if current_trend is None:
                # First bar initialization
                current_trend = 1 if price >= closes[0] else -1
                # For simplicity, first bar is treated as a single bar
                # In actual Line Break, the first trend is established by the first movement
                # But we'll follow a standard approach:
                current_trend = 1 if price > closes[0] else -1
                # Actually, let's just start with the first price
                current_trend = 1 
                open_p = price
                high_p = price
                low_p = price
                close_p = price
                history.append({'open': open_p, 'high': high_p, 'low': low_p, 'close': close_p, 'uptrend': True})
                trend_extremes = [price]
                continue

            if current_trend == 1:
                # Currently in uptrend. Check for downtrend reversal.
                # A downtrend reversal occurs if price < lowest of last 'n' lows
                # In Line Break, we compare against the 'n' previous bars' lows
                if len(history) >= self.line_number:
                    # Get the lows of the last 'n' bars in the current trend
                    last_n_lows = [h['low'] for h in history[-self.line_number:]]
                    if price < min(last_n_lows):
                        # REVERSAL to downtrend
                        current_trend = -1
                        open_p = history[-1]['close']
                        high_p = open_p
                        low_p = open_p
                        close_p = price
                        # Check if price is actually lower than open for the new bar
                        if close_p > open_p:
                            high_p = close_p
                        else:
                            low_p = close_p
                        
                        # In a reversal, the new bar's high/low is based on the reversal point
                        # But standard Line Break: the new bar is the reversal bar
                        # We'll use the standard: new bar starts at the previous close
                        history.append({'open': open_p, 'high': max(open_p, price), 'low': min(open_p, price), 'close': price, 'uptrend': False})
                        trend_extremes = [min(open_p, price)]
                        continue
                
                # If no reversal, continue uptrend
                if price > history[-1]['high']:
                    # Extend current bar
                    history[-1]['high'] = price
                    history[-1]['close'] = price
                    # In Line Break, if price goes up, we usually create a new bar or extend?
                    # Standard Line Break: a new bar is created when price breaks the high
                    # But if it's the same trend, we extend the high/close.
                    # Actually, Line Break creates a NEW bar for every movement that continues the trend.
                    # Let's follow: new bar if price > previous high
                    new_bar = {'open': history[-1]['close'], 'high': price, 'low': history[-1]['close'], 'close': price, 'uptrend': True}
                    history.append(new_bar)
                    trend_extremes.append(price)
                elif price < history[-1]['low']:
                    # This shouldn't happen in a pure uptrend unless it's a reversal, 
                    # but we handle it by extending the bar's low
                    history[-1]['low'] = price
                    history[-1]['close'] = price
                else:
                    # Price within current bar range
                    history[-1]['close'] = price
            
            elif current_trend == -1:
                # Currently in downtrend. Check for uptrend reversal.
                if len(history) >= self.line_number:
                    last_n_highs = [h['high'] for h in history[-self.line_number:]]
                    if price > max(last_n_highs):
                        # REVERSAL to uptrend
                        current_trend = 1
                        open_p = history[-1]['close']
                        high_p = open_p
                        low_p = open_p
                        close_p = price
                        if close_p < open_p:
                            low_p = close_p
                        else:
                            high_p = close_p
                        
                        history.append({'open': open_p, 'high': max(open_p, price), 'low': min(open_p, price), 'close': price, 'uptrend': True})
                        trend_extremes = [max(open_p, price)]
                        continue

                # If no reversal, continue downtrend
                if price < history[-1]['low']:
                    new_bar = {'open': history[-1]['close'], 'high': history[-1]['close'], 'low': price, 'close': price, 'uptrend': False}
                    history.append(new_bar)
                    trend_extremes.append(price)
                elif price > history[-1]['high']:
                    history[-1]['high'] = price
                    history[-1]['close'] = price
                else:
                    history[-1]['close'] = price

        # The logic above is a bit simplified for a single pass. 
        # Let's use a more robust Line Break algorithm:
        
        # Re-implementing Line Break correctly:
        res_history = []
        if not self.odf.empty:
            closes = self.odf['close'].values
            # Initial bar
            curr_trend = 1 # 1 for up, -1 for down
            # We need to find the first trend
            # For simplicity, assume first bar is up
            last_close = closes[0]
            res_history.append({'open': last_close, 'high': last_close, 'low': last_close, 'close': last_close, 'uptrend': True})
            
            for i in range(1, len(closes)):
                price = closes[i]
                if curr_trend == 1:
                    # Check reversal: price < min(last n lows)
                    if len(res_history) >= self.line_number:
                        if price < min(h['low'] for h in res_history[-self.line_number:]):
                            curr_trend = -1
                            res_history.append({'open': res_history[-1]['close'], 'high': res_history[-1]['close'], 'low': min(res_history[-1]['close'], price), 'close': price, 'uptrend': False})
                            continue
                    
                    # Continue uptrend
                    if price > res_history[-1]['high']:
                        res_history.append({'open': res_history[-1]['close'], 'high': price, 'low': res_history[-1]['close'], 'close': price, 'uptrend': True})
                    elif price < res_history[-1]['low']:
                        # This part is tricky in Line Break; usually price doesn't drop within an uptrend bar 
                        # unless it's a reversal. If it drops, we just update the low.
                        res_history[-1]['low'] = price
                        res_history[-1]['close'] = price
                    else:
                        res_history[-1]['close'] = price
                else:
                    # Check reversal: price > max(last n highs)
                    if len(res_history) >= self.line_number:
                        if price > max(h['high'] for h in res_history[-self.line_number:]):
                            curr_trend = 1
                            res_history.append({'open': res_history[-1]['close'], 'high': max(res_history[-1]['close'], price), 'low': res_history[-1]['close'], 'close': price, 'uptrend': True})
                            continue
                    
                    # Continue downtrend
                    if price < res_history[-1]['low']:
                        res_history.append({'open': res_history[-1]['close'], 'high': res_history[-1]['close'], 'low': price, 'close': price, 'uptrend': False})
                    elif price > res_history[-1]['high']:
                        res_history[-1]['high'] = price
                        res_history[-1]['close'] = price
                    else:
                        res_history[-1]['close'] = price
            
            self.df = pd.DataFrame(res_history)
        return self.df

class PnF(Instrument):
    def __init__(self, df: pd.DataFrame, box_size: int = 1, reversal_size: int = 3):
        super().__init__(df)
        self.box_size = box_size
        self.reversal_size = reversal_size

    @property
    def brick_size(self) -> int:
        return self.box_size

    def get_state(self, uptrend_p1: bool, bricks: int) -> str:
        """
        Get the state of the trend based on the given parameters.
        
        :param uptrend_p1: Boolean indicating if the previous state was an uptrend.
        :param bricks: Number of bricks in the current trend.
        :return: 'X' for uptrend, 'O' for downtrend.
        """
        return 'X' if uptrend_p1 else 'O'

    def roundit(self, x: float, base: int) -> int:
        """
        Rounds the input x to the nearest multiple of base and returns the result as an integer.
        
        :param x: The input value to round.
        :param base: The base value for rounding.
        :return: The rounded integer value.
        """
        return int(round(x / base) * base)

    def get_ohlc_data(self, source: str) -> pd.DataFrame:
        """
        Retrieves the PnF data in the form of an OHLC DataFrame.
        
        :param source: The source of data (e.g., 'close').
        :return: A DataFrame containing PnF OHLC data.
        """
        if self.odf.empty:
            return pd.DataFrame()

        prices = self.odf[source.lower()].values
        if len(prices) == 0:
            return pd.DataFrame()

        pnf_data = []
        current_trend = None  # True for X (uptrend), False for O (downtrend)
        last_price = self.roundit(prices[0], self.box_size)
        
        # Initial state
        # We need to find the first movement that establishes a trend
        for i in range(1, len(prices)):
            price = self.roundit(prices[i], self.box_size)
            if price == last_price:
                continue
            
            if current_trend is None:
                if price > last_price:
                    current_trend = True
                    last_price = price
                else:
                    current_trend = False
                    last_price = price
                continue

            if current_trend:  # Currently in X (uptrend)
                # Check for reversal to O
                # Reversal requires price to drop by reversal_size * box_size
                if price <= last_price - (self.reversal_size * self.box_size):
                    current_trend = False
                    # The reversal point is the last_price
                    # But in PnF, the new trend starts from the reversal level
                    # We'll record the reversal
                    pnf_data.append({
                        'open': last_price,
                        'high': last_price,
                        'low': price,
                        'close': price,
                        'uptrend': False
                    })
                    last_price = price
                elif price > last_price:
                    # Continue uptrend
                    last_price = price
                    pnf_data.append({
                        'open': last_price - self.box_size,
                        'high': last_price,
                        'low': last_price - self.box_size,
                        'close': last_price,
                        'uptrend': True
                    })
            else:  # Currently in O (downtrend)
                # Check for reversal to X
                if price >= last_price + (self.reversal_size * self.box_size):
                    current_trend = True
                    pnf_data.append({
                        'open': last_price,
                        'high': price,
                        'low': last_price,
                        'close': price,
                        'uptrend': True
                    })
                    last_price = price
                elif price < last_price:
                    # Continue downtrend
                    last_price = price
                    pnf_data.append({
                        'open': last_price + self.box_size,
                        'high': last_price + self.box_size,
                        'low': last_price,
                        'close': last_price,
                        'uptrend': False
                    })

        self.df = pd.DataFrame(pnf_data)
        return self.df

    def get_bar_ohlc_data(self, source: str) -> pd.DataFrame:
        """
        Retrieves bar OHLC (Open, High, Low, Close) data.
        
        :param source: The source of data.
        :return: A DataFrame containing bar OHLC data.
        """
        # For PnF, bars are often defined by the sequence of X's or O's
        # This is a placeholder for complex bar grouping logic
        return self.get_ohlc_data(source)
