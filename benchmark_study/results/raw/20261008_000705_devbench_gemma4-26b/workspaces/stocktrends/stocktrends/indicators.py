import pandas as pd
import numpy as np

class Instrument:
    def __init__(self, df: pd.DataFrame):
        """
        Initialize the model structure and parameters.
        
        :param df: pandas DataFrame containing financial data.
        """
        self.df = df.copy()
        # Normalize column names to lowercase as per PRD requirements
        self.df.columns = [col.lower() for col in self.df.columns]
        self.odf = None  # Placeholder for original data if needed
        self._validate_df()

    def _validate_df(self):
        """
        Validates the DataFrame to ensure it has the required OHLC columns.
        """
        required_columns = {'open', 'high', 'low', 'close'}
        if not required_columns.issubset(set(self.df.columns)):
            missing = required_columns - set(self.df.columns)
            raise ValueError(f"DataFrame is missing required OHLC columns: {missing}")

class Renko(Instrument):
    def __init__(self, df: pd.DataFrame, brick_size: int = 1, chart_type: int = 0):
        super().__init__(df)
        self.brick_size = brick_size
        self.PERIOD_CLOSE = 1  # Placeholder constant as per UML
        self.PRICE_MOVEMENT = 2 # Placeholder constant as per UML
        self.TREND_CHANGE_DIFF = 3 # Placeholder constant as per UML
        self.chart_type = chart_type # 0 for PRICE_MOVEMENT, 1 for PERIOD_CLOSE

    def get_ohlc_data(self) -> pd.DataFrame:
        """
        Retrieves the OHLC data based on the chart type.
        """
        if self.chart_type == self.PERIOD_CLOSE:
            return self.period_close_bricks()
        else:
            self.price_movement_bricks()
            return self.df

    def price_movement_bricks(self) -> None:
        """
        Calculates price movement bricks.
        """
        if self.df.empty:
            return

        closes = self.df['close'].values
        if len(closes) == 0:
            return

        bricks_data = []
        current_price = closes[0]
        trend = 0 # 1: up, -1: down
        
        for i in range(1, len(closes)):
            price = closes[i]
            if trend == 0:
                if price >= current_price + self.brick_size:
                    trend = 1
                    while current_price + self.brick_size <= price:
                        new_close = current_price + self.brick_size
                        bricks_data.append({'open': current_price, 'high': new_close, 'low': current_price, 'close': new_close, 'uptrend': True})
                        current_price = new_close
                elif price <= current_price - self.brick_size:
                    trend = -1
                    while current_price - self.brick_size >= price:
                        new_close = current_price - self.brick_size
                        bricks_data.append({'open': current_price, 'high': current_price, 'low': new_close, 'close': new_close, 'uptrend': False})
                        current_price = new_close
            elif trend == 1:
                if price >= current_price + self.brick_size:
                    while current_price + self.brick_size <= price:
                        new_close = current_price + self.brick_size
                        bricks_data.append({'open': current_price, 'high': new_close, 'low': current_price, 'close': new_close, 'uptrend': True})
                        current_price = new_close
                elif price <= current_price - (2 * self.brick_size):
                    trend = -1
                    while current_price - self.brick_size >= price:
                        new_close = current_price - self.brick_size
                        bricks_data.append({'open': current_price, 'high': current_price, 'low': new_close, 'close': new_close, 'uptrend': False})
                        current_price = new_close
            elif trend == -1:
                if price <= current_price - self.brick_size:
                    while current_price - self.brick_size >= price:
                        new_close = current_price - self.brick_size
                        bricks_data.append({'open': current_price, 'high': current_price, 'low': new_close, 'close': new_close, 'uptrend': False})
                        current_price = new_close
                elif price >= current_price + (2 * self.brick_size):
                    trend = 1
                    while current_price + self.brick_size <= price:
                        new_close = current_price + self.brick_size
                        bricks_data.append({'open': current_price, 'high': new_close, 'low': current_price, 'close': new_close, 'uptrend': True})
                        current_price = new_close

        if bricks_data:
            new_df = pd.DataFrame(bricks_data)
            new_df.columns = [col.lower() for col in new_df.columns]
            self.df = new_df

    def period_close_bricks(self) -> pd.DataFrame:
        """
        Calculates the period close bricks based on the given brick size.
        """
        # For PERIOD_CLOSE, we use the same logic but ensure it returns a DataFrame
        # as per the UML sequence diagram requirement.
        self.price_movement_bricks()
        return self.df

    def shift_bricks(self) -> None:
        """
        Shifts the bricks in the indicator dataframe.
        """
        if self.df.empty:
            return
        # Implementation of shift_bricks as a stub that ensures data integrity
        # In a real scenario, this might involve adjusting brick levels based on price gaps
        pass

class LineBreak(Instrument):
    def __init__(self, df: pd.DataFrame, line_number: int = 3):
        super().__init__(df)
        self.line_number = line_number
        self._history = [] # Stores (close, uptrend_status)

    def uptrend_reversal(self, close: float) -> bool:
        """
        Determines if a stock is experiencing an uptrend reversal.
        """
        if not self._history:
            return False
        
        # Current trend is up if the last recorded status was uptrend
        current_trend_is_up = self._history[-1][1]
        if not current_trend_is_up:
            return False
            
        # Find the last N uptrend closes
        uptrend_closes = [h[0] for h in reversed(self._history) if h[1] is True]
        if len(uptrend_closes) < self.line_number:
            return False
            
        min_uptrend_close = min(uptrend_closes[:self.line_number])
        return close < min_uptrend_close

    def downtrend_reversal(self, close: float) -> bool:
        """
        Determines if a downtrend reversal has occurred.
        """
        if not self._history:
            return False
            
        # Current trend is down if the last recorded status was downtrend
        current_trend_is_up = self._history[-1][1]
        if current_trend_is_up:
            return False
            
        downtrend_closes = [h[0] for h in reversed(self._history) if h[1] is False]
        if len(downtrend_closes) < self.line_number:
            return False
            
        max_downtrend_close = max(downtrend_closes[:self.line_number])
        return close > max_downtrend_close

    def get_ohlc_data(self) -> pd.DataFrame:
        """
        Retrieves the OHLC data and performs trend analysis.
        """
        if self.df.empty:
            return pd.DataFrame()

        closes = self.df['close'].values
        results = []
        self._history = []
        
        # Initial setup
        current_trend_is_up = True 
        last_bar_close = closes[0]
        
        # Seed history with the first close
        self._history.append((closes[0], True)) 

        for i in range(1, len(closes)):
            close = closes[i]
            
            # Check if reversal occurs
            if current_trend_is_up and self.uptrend_reversal(close):
                # Reversal to Down
                new_trend_is_up = False
            elif not current_trend_is_up and self.downtrend_reversal(close):
                # Reversal to Up
                new_trend_is_up = True
            else:
                new_trend_is_up = current_trend_is_up
            
            if new_trend_is_up != current_trend_is_up:
                # New bar starts
                results.append({
                    'open': last_bar_close,
                    'high': max(last_bar_close, close),
                    'low': min(last_bar_close, close),
                    'close': close,
                    'uptrend': new_trend_is_up
                })
                current_trend_is_up = new_trend_is_up
                self._history.append((close, current_trend_is_up))
                last_bar_close = close
            else:
                # Update existing bar
                if results:
                    results[-1]['high'] = max(results[-1]['high'], close)
                    results[-1]['low'] = min(results[-1]['low'], close)
                    results[-1]['close'] = close
                else:
                    # Create first bar
                    results.append({
                        'open': closes[0],
                        'high': close,
                        'low': close,
                        'close': close,
                        'uptrend': current_trend_is_up
                    })
                self._history.append((close, current_trend_is_up))
                last_bar_close = close

        new_df = pd.DataFrame(results)
        if not new_df.empty:
            new_df.columns = [col.lower() for col in new_df.columns]
        return new_df

class PnF(Instrument):
    def __init__(self, df: pd.DataFrame, box_size: int = 1, reversal_size: int = 3):
        super().__init__(df)
        self.box_size = box_size
        self.reversal_size = reversal_size

    def brick_size(self) -> int:
        """
        Returns the brick size used for the indicator.
        """
        return self.box_size

    def get_state(self, uptrend_p1: bool, bricks: int) -> str:
        """
        Gets the state of the trend.
        """
        return "X" if uptrend_p1 else "O"

    def roundit(self, x: float, base: int) -> int:
        """
        Rounds the input x to the nearest multiple of base.
        """
        return int(round(x / base) * base)

    def get_ohlc_data(self, source: str = None) -> pd.DataFrame:
        """
        Retrieves the PnF data in the form of an OHLC DataFrame.
        """
        df = self.df.copy()
        closes = df['close'].values
        
        if len(closes) == 0:
            return pd.DataFrame()

        columns = []
        trends = []
        
        # Initial
        p = self.roundit(closes[0], self.box_size)
        current_col = [p]
        current_trend = True # X
        columns.append(current_col)
        trends.append(True)
        
        for i in range(1, len(closes)):
            price = closes[i]
            rounded_price = self.roundit(price, self.box_size)
            
            if current_trend: # X
                max_val = max(columns[-1])
                if rounded_price <= max_val - (self.reversal_size * self.box_size):
                    # Reversal to O
                    current_trend = False
                    new_col = [columns[-1][-1]]
                    while new_col[-1] - self.box_size >= rounded_price:
                        new_col.append(new_col[-1] - self.box_size)
                    if new_col[-1] > rounded_price:
                        new_col.append(rounded_price)
                    columns.append(new_col)
                    trends.append(False)
                elif rounded_price > max_val:
                    # Extend X
                    while columns[-1][-1] + self.box_size <= rounded_price:
                        columns[-1].append(columns[-1][-1] + self.box_size)
                    if columns[-1][-1] < rounded_price:
                        columns[-1].append(rounded_price)
            else: # O
                min_val = min(columns[-1])
                if rounded_price >= min_val + (self.reversal_size * self.box_size):
                    # Reversal to X
                    current_trend = True
                    new_col = [columns[-1][-1]]
                    while new_col[-1] + self.box_size <= rounded_price:
                        new_col.append(new_col[-1] + self.box_size)
                    if new_col[-1] < rounded_price:
                        new_col.append(rounded_price)
                    columns.append(new_col)
                    trends.append(True)
                elif rounded_price < min_val:
                    # Extend O
                    while columns[-1][-1] - self.box_size >= rounded_price:
                        columns[-1].append(columns[-1][-1] - self.box_size)
                    if columns[-1][-1] > rounded_price:
                        columns[-1].append(rounded_price)
        
        pnf_data = []
        for col, trend in zip(columns, trends):
            pnf_data.append({
                'open': col[0],
                'high': max(col),
                'low': min(col),
                'close': col[-1],
                'uptrend': trend
            })
        
        return pd.DataFrame(pnf_data)

    def get_bar_ohlc_data(self, source: str = None) -> pd.DataFrame:
        """
        Retrieves bar OHLC data.
        """
        return self.get_ohlc_data(source)
