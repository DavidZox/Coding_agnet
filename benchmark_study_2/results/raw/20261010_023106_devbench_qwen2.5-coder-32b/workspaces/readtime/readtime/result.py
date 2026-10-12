class Result:
    def __init__(self, seconds, wpm=265):
        self._delta = seconds
        self._wpm = wpm
        self._add_operator_methods()

    def __repr__(self):
        return f"Result(seconds={self._delta}, wpm={self._wpm})"

    def __str__(self):
        return self.text()

    @property
    def seconds(self):
        return self._delta

    @property
    def minutes(self):
        return self._delta / 60

    def text(self):
        if self._delta < 60:
            return f"{self._delta} seconds"
        else:
            return f"{self.minutes:.2f} minutes"

    def _add_operator_methods(self):
        operators = {
            '__add__': lambda x: self.seconds + x.seconds,
            '__sub__': lambda x: self.seconds - x.seconds,
            '__mul__': lambda x: self.seconds * x,
            '__truediv__': lambda x: self.seconds / x,
            '__floordiv__': lambda x: self.seconds // x,
            '__mod__': lambda x: self.seconds % x,
            '__lt__': lambda x: self.seconds < x.seconds,
            '__le__': lambda x: self.seconds <= x.seconds,
            '__eq__': lambda x: self.seconds == x.seconds,
            '__ne__': lambda x: self.seconds != x.seconds,
            '__gt__': lambda x: self.seconds > x.seconds,
            '__ge__': lambda x: self.seconds >= x.seconds,
        }
        for op in operators:
            self._create_method(op)

    def _create_method(self, op):
        def method(self, other):
            operators = {
                '__add__': lambda x: self.seconds + x.seconds,
                '__sub__': lambda x: self.seconds - x.seconds,
                '__mul__': lambda x: self.seconds * x,
                '__truediv__': lambda x: self.seconds / x,
                '__floordiv__': lambda x: self.seconds // x,
                '__mod__': lambda x: self.seconds % x,
                '__lt__': lambda x: self.seconds < x.seconds,
                '__le__': lambda x: self.seconds <= x.seconds,
                '__eq__': lambda x: self.seconds == x.seconds,
                '__ne__': lambda x: self.seconds != x.seconds,
                '__gt__': lambda x: self.seconds > x.seconds,
                '__ge__': lambda x: self.seconds >= x.seconds,
            }
            if isinstance(other, Result):
                func = operators[op]
                return Result(func(other), self._wpm)
            elif isinstance(other, (int, float)):
                func = operators[op]
                return Result(func(other), self._wpm)
            else:
                return NotImplemented
        setattr(Result, op, method.__get__(self))
