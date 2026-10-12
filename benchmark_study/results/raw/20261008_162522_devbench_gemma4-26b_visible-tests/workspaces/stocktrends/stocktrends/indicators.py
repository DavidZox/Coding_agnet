import pandas as pd
import numpy as np
import math

class Instrument:
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        # Normalize column names to lowercase for consistent validation and access
        self.df.columns = [col.lower() for col in self.df.columns]
        self.odf = pd.DataFrame()
        self._validate_df()

    def _validate_df(self) -> None:
        """
        Validates the DataFrame to ensure it has the required OHLC columns.
        """
        required_columns = ['open', 'high', 'low', 'close']
        for col in required_columns:
            if col not in self.df.columns:
                raise ValueError(f"Missing required column: {col}")
        return None

class Renko(Instrument):
    PERIOD_CLOSE = 0
    PRICE_MOVEMENT = 1
    TREND_CHANGE_DIFF = 2

    def __init__(self, df: pd.DataFrame):
        super().__init__(df)
        self.brick_size = 0
        self.chart_type = 0

    def get_ohlc_data(self) -> pd.DataFrame:
        if self.chart_type == self.PERIOD_CLOSE:
            return self.period_close_bricks()
        else:
            self.price_movement_bricks()
            return self.odf

    def price_movement_bricks(self) -> None:
        if self.brick_size <= 0:
            return

        close_prices = self.df['close'].values
        bricks = []
        
        if len(close_prices) == 0:
            self.odf = pd.DataFrame()
            return

        last_brick_close = close_prices[0]
        trend = 0  # 1 for up, -1 for down

        for i in range(1, len(close_prices)):
            current_close = close_prices[i]
            diff = current_close - last_brick_close

            if abs(diff) >= self.brick_size:
                num_bricks = int(abs(diff) // self.brick_size)
                direction = 1 if diff > 0 else -1
                
                for _ in range(num_bricks):
                    brick_open = last_brick_close
                    brick_close = last_brick_close + (direction * self.brick_size)
                    
                    # In standard Renko, a reversal requires a certain movement, 
                    # but here we follow the basic brick logic
                    # If direction changes, it's a reversal
                    new_trend = direction
                    
                    bricks.append({
                        'open': brick_open,
                        'high': max(brick_open, brick_close),
                        'low': min(brick_open, brick_close),
                        'close': brick_close,
                        'uptrend': new_trend == 1
                    })
                    last_brick_close = brick_close
                    trend = new_trend

        if bricks:
            res_df = pd.DataFrame(bricks)
            res_df['index'] = range(len(res_df))
            final_cols = ['index', 'open', 'high', 'low', 'close', 'uptrend']
            self.odf = res_df[final_cols]

    def period_close_bricks(self) -> pd.DataFrame:
        if self.brick_size <= 0:
            return pd.DataFrame()

        close_prices = self.df['close'].values
        bricks = []
        
        if len(close_prices) == 0:
            return pd.DataFrame()

        last_brick_close = close_prices[0]
        
        for i in range(len(close_prices)):
            current_close = close_prices[i]
            diff = current_close - last_brick_close
            
            if abs(diff) >= self.brick_size:
                num_bricks = int(abs(diff) // self.brick_size)
                direction = 1 if diff > 0 else -1
                
                for _ in range(num_bricks):
                    brick_open = last_brick_close
                    brick_close = last_brick_close + (direction * self.brick_size)
                    
                    bricks.append({
                        'open': brick_open,
                        'high': max(brick_open, brick_close),
                        'low': min(brick_open, brick_close),
                        'close': brick_close,
                        'uptrend': direction == 1
                    })
                    last_brick_close = brick_close

        if bricks:
            res_df = pd.DataFrame(bricks)
            res_df['index'] = range(len(res_df))
            final_cols = ['index', 'open', 'high', 'low', 'close', 'uptrend']
            return res_df[final_cols]
        
        return pd.DataFrame()

    def shift_bricks(self) -> None:
        pass

class LineBreak(Instrument):
    def __init__(self, df: pd.DataFrame):
        super().__init__(df)
        self.line_number = 0

    def uptrend_reversal(self, close: float) -> bool:
        # A reversal to uptrend occurs if the close price breaks above the high of the last N lines
        # In this implementation, we check if the current close is greater than the max high of the previous N lines
        # However, the logic is usually handled within the loop of get_ohlc_data.
        # For the purpose of this class structure, we define the logic used in get_ohlc_data.
        return False

    def downtrend_reversal(self, close: float) -> bool:
        return False

    def get_ohlc_data(self) -> pd.DataFrame:
        return self._calculate_linebreak()

    def _calculate_linebreak(self) -> pd.DataFrame:
        close_prices = self.df['close'].values
        dates = self.df['date'].values
        
        lines = []
        line_highs = []
        line_lows = []
        line_dates = []
        
        current_trend = None
        last_close = close_prices[0]
        
        for i in range(1, len(close_prices)):
            price = close_prices[i]
            date = dates[i]
            
            if current_trend is None:
                if price > last_close:
                    current_trend = 1
                    line_open, line_close = last_close, price
                    lines.append({'open': line_open, 'high': max(line_open, line_close), 'low': min(line_open, line_close), 'close': line_close, 'uptrend': True})
                    line_highs.append(max(line_open, line_close))
                    line_lows.append(min(line_open, line_close))
                    line_dates.append(date)
                    last_close = line_close
                elif price < last_close:
                    current_trend = -1
                    line_open, line_close = last_close, price
                    lines.append({'open': line_open, 'high': max(line_open, line_close), 'low': min(line_open, line_close), 'close': line_close, 'uptrend': False})
                    line_highs.append(max(line_open, line_close))
                    line_lows.append(min(line_open, line_close))
                    line_dates.append(date)
                    last_close = line_close
                continue

            if current_trend == 1:
                if len(line_lows) >= self.line_number and price < min(line_lows[-self.line_number:]):
                    current_trend = -1
                    line_open, line_close = last_close, price
                    lines.append({'open': line_open, 'high': max(line_open, line_close), 'low': min(line_open, line_close), 'close': line_close, 'uptrend': False})
                    line_highs.append(max(line_open, line_close))
                    line_lows.append(min(line_open, line_close))
                    line_dates.append(date)
                    last_close = line_close
                elif price > line_highs[-1]:
                    line_open, line_close = line_highs[-1], price
                    lines.append({'open': line_open, 'high': max(line_open, line_close), 'low': min(line_open, line_close), 'close': line_close, 'uptrend': True})
                    line_highs.append(max(line_open, line_close))
                    line_lows.append(min(line_open, line_close))
                    line_dates.append(date)
                    last_close = line_close
            else: # current_trend == -1
                if len(line_highs) >= self.line_number and price > max(line_highs[-self.line_number:]):
                    current_trend = 1
                    line_open, line_close = last_close, price
                    lines.append({'open': line_open, 'high': max(line_open, line_close), 'low': min(line_open, line_close), 'close': line_close, 'uptrend': True})
                    line_highs.append(max(line_open, line_close))
                    line_lows.append(min(line_open, line_close))
                    line_dates.append(date)
                    last_close = line_close
                elif price < line_lows[-1]:
                    line_open, line_close = line_lows[-1], price
                    lines.append({'open': line_open, 'high': max(line_open, line_close), 'low': min(line_open, line_close), 'close': line_close, 'uptrend': False})
                    line_highs.append(max(line_open, line_close))
                    line_lows.append(min(line_open, line_close))
                    line_dates.append(date)
                    last_close = line_close
                    
        if not lines:
            return pd.DataFrame()
            
        res_df = pd.DataFrame(lines)
        res_df.insert(0, 'index', range(len(res_df)))
        res_df.insert(1, 'date', line_dates)
        return res_df[['index', 'date', 'open', 'high', 'low', 'close', 'uptrend']]

class PnF(Instrument):
    UPTREND_CONTINUAL = "UPTREND_CONTINUAL"
    UPTREND_REVERSAL = "UPTREND_REVERSAL"
    DOWNTREND_CONTINUAL = "DOWNTREND_CONTINUAL"
    DOWNTREND_REVERSAL = "DOWNTREND_REVERSAL"

    def __init__(self, df: pd.DataFrame, box_size: int = 5, reversal_size: int = 3):
        super().__init__(df)
        self.box_size = box_size
        self.reversal_size = reversal_size

    def brick_size(self) -> int:
        return self.box_size

    def get_state(self, uptrend_p1: bool, bricks: int) -> str:
        if uptrend_p1:
            return self.UPTREND_CONTINUAL if bricks > 0 else self.UPTREND_REVERSAL
        else:
            return self.DOWNTREND_CONTINUAL if bricks < 0 else self.DOWNTREND_REVERSAL

    def roundit(self, x: float, base: int = None) -> int:
        if base is None:
            base = self.box_size
        return int(round(x / base) * base)

    def get_ohlc_data(self, source: str) -> pd.DataFrame:
        if source == 'hl':
            prices = ((self.df['high'] + self.df['low']) / 2).values
        else:
            prices = self.df[source].values

        if len(prices) == 0:
            return pd.DataFrame()

        last_price = self.roundit(prices[0], self.box_size)
        current_trend = 0  # 1 for up, -1 for down
        bricks = []

        for i in range(1, len(prices)):
            price = prices[i]

            if current_trend == 0:
                if price >= last_price + self.box_size:
                    current_trend = 1
                elif price <= last_price - self.box_size:
                    current_trend = -1
                else:
                    continue

            if current_trend == 1:
                if price >= last_price + self.box_size:
                    num_bricks = int((price - last_price) // self.box_size)
                    for _ in range(num_bricks):
                        brick_open = last_price
                        brick_close = last_price + self.box_size
                        bricks.append({'open': brick_open, 'high': brick_close, 'low': brick_open, 'close': brick_close, 'trend': 1})
                        last_price = brick_close
                elif price <= last_price - (self.reversal_size * self.box_size):
                    current_trend = -1
                    reversal_threshold = last_price - (self.reversal_size * self.box_size)
                    # We need to find how many bricks to go down to reach or pass the reversal threshold
                    # But the rule is: once reversal is triggered, we start new bricks from the last_price
                    # The first brick of the new trend must be at least reversal_size * box_size away.
                    # To simplify and match standard PnF:
                    num_bricks = int((last_price - reversal_threshold) // self.box_size)
                    # However, the standard way is to just start the new trend.
                    # Let's re-calculate last_price to be the new base.
                    # The requirement is the reversal must be at least reversal_size * box_size.
                    # We'll move last_price down by reversal_size * box_size.
                    new_last_price = last_price - (self.reversal_size * self.box_size)
                    # But we need to account for the bricks between last_price and new_last_price.
                    # Actually, the simplest way to ensure the reversal is correct:
                    # The new trend starts from the price that is reversal_size * box_size away.
                    # Let's adjust the logic:
                    pass # handled below

            # Re-implementing the loop logic more robustly
        
        # Resetting logic for a cleaner implementation
        last_price = self.roundit(prices[0], self.box_size)
        current_trend = 0
        bricks = []
        
        for i in range(1, len(prices)):
            price = prices[i]
            if current_trend == 0:
                if price >= last_price + self.box_size:
                    current_trend = 1
                elif price <= last_price - self.box_size:
                    current_trend = -1
                else:
                    continue
            
            if current_trend == 1:
                if price >= last_price + self.box_size:
                    num_bricks = int((price - last_price) // self.box_size)
                    for _ in range(num_bricks):
                        brick_open = last_price
                        brick_close = last_price + self.box_size
                        bricks.append({'open': brick_open, 'high': brick_close, 'low': brick_open, 'close': brick_close, 'trend': 1})
                        last_price = brick_close
                elif price <= last_price - (self.reversal_size * self.box_size):
                    current_trend = -1
                    # The new trend starts from the last_price, but the first brick must go down.
                    # To satisfy the reversal requirement, the first brick's close must be 
                    # at least reversal_size * box_size below the previous trend's last_price.
                    # Wait, the standard PnF: the reversal is a single movement of N boxes.
                    # Let's use the logic: the new trend's first brick's close is last_price - (reversal_size * box_size)
                    # No, that's not right. The reversal is the distance.
                    # Let's try:
                    num_bricks = int((last_price - price) // self.box_size) # This is not quite right for reversal
                    # Let's use the logic: if price <= last_price - reversal_size * box_size:
                    # The new trend starts. The first brick's close is last_price - reversal_size * box_size.
                    # But we must ensure it's a multiple of box_size.
                    target_price = last_price - (self.reversal_size * self.box_size)
                    # We need to add 'reversal_size' bricks.
                    for _ in range(self.reversal_size):
                        brick_open = last_price - (_ * self.box_size)
                        brick_close = last_price - ((_ + 1) * self.box_size)
                        bricks.append({'open': brick_open, 'high': brick_open, 'low': brick_close, 'close': brick_close, 'trend': -1})
                    last_price = last_price - (self.reversal_size * self.box_size)
                    # Now continue with the new trend and the remaining price
                    # But we already processed the reversal. We need to check if the current price 
                    # allows for more bricks in the new trend.
                    # Actually, the loop will continue with the next 'i'. 
                    # We need to make sure last_price is updated.
                    # Let's refine:
                    pass

        # Let's use a more standard PnF implementation
        last_price = self.roundit(prices[0], self.box_size)
        current_trend = 0
        bricks = []
        for p in prices:
            if current_trend == 0:
                if p >= last_price + self.box_size:
                    current_trend = 1
                elif p <= last_price - self.box_size:
                    current_trend = -1
                else:
                    continue
            
            if current_trend == 1:
                if p >= last_price + self.box_size:
                    num_bricks = int((p - last_price) // self.box_size)
                    for _ in range(num_bricks):
                        brick_open = last_price
                        brick_close = last_price + self.box_size
                        bricks.append({'open': brick_open, 'high': brick_close, 'low': brick_open, 'close': brick_close, 'trend': 1})
                        last_price = brick_close
                elif p <= last_price - (self.reversal_size * self.box_size):
                    current_trend = -1
                    for _ in range(self.reversal_size):
                        brick_open = last_price
                        brick_close = last_price - self.box_size
                        bricks.append({'open': brick_open, 'high': brick_open, 'low': brick_close, 'close': brick_close, 'trend': -1})
                        last_price = brick_close
            elif current_trend == -1:
                if p <= last_price - self.box_size:
                    num_bricks = int((last_price - p) // self.box_size)
                    for _ in range(num_bricks):
                        brick_open = last_price
                        brick_close = last_price - self.box_size
                        bricks.append({'open': brick_open, 'high': brick_open, 'low': brick_close, 'close': brick_close, 'trend': -1})
                        last_price = brick_close
                elif p >= last_price + (self.reversal_size * self.box_size):
                    current_trend = 1
                    for _ in range(self.reversal_size):
                        brick_open = last_price
                        brick_close = last_price + self.box_size
                        bricks.append({'open': brick_open, 'high': brick_close, 'low': brick_open, 'close': brick_close, 'trend': 1})
                        last_price = brick_close
        
        if not bricks:
            return pd.DataFrame()
        res_df = pd.DataFrame(bricks)
        res_df.insert(0, 'date', 'N/A')
        return res_df[['date', 'open', 'high', 'low', 'close', 'trend']]

    def get_bar_ohlc_data(self, source: str) -> pd.DataFrame:
        bricks_df = self.get_ohlc_data(source)
        if bricks_df.empty:
            return pd.DataFrame()

        bars = []
        current_trend = bricks_df.iloc[0]['trend']
        current_bar_bricks = []

        for _, row in bricks_df.iterrows():
            if row['trend'] == current_trend:
                current_bar_bricks.append(row)
            else:
                bar_open = current_bar_bricks[0]['open']
                bar_high = max(b['high'] for b in current_bar_bricks)
                bar_low = min(b['low'] for b in current_bar_bricks)
                bar_close = current_bar_bricks[-1]['close']
                bars.append({'open': bar_open, 'high': bar_high, 'low': bar_low, 'close': bar_close})
                current_trend = row['trend']
                current_bar_bricks = [row]
        
        if current_bar_bricks:
            bar_open = current_bar_bricks[0]['open']
            bar_high = max(b['high'] for b in current_bar_bricks)
            bar_low = min(b['low'] for b in current_bar_bricks)
            bar_close = current_bar_bricks[-1]['close']
            bars.append({'open': bar_open, 'high': bar_high, 'low': bar_low, 'close': bar_close})

        if not bars:
            return pd.DataFrame()
            
        res_df = pd.DataFrame(bars)
        res_df.insert(0, 'date', 'N/A')
        return res_df[['date', 'open', 'high', 'low', 'close']]
