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
            '__add__': lambda x, y: Result(x._delta + y._delta, x._wpm),
            '__sub__': lambda x, y: Result(x._delta - y._delta, x._wpm),
            '__mul__': lambda x, y: Result(x._delta * y, x._wpm),
            '__truediv__': lambda x, y: Result(x._delta / y, x._wpm),
            '__eq__': lambda x, y: x._delta == y._delta,
            '__ne__': lambda x, y: x._delta != y._delta,
            '__lt__': lambda x, y: x._delta < y._delta,
            '__le__': lambda x, y: x._delta <= y._delta,
            '__gt__': lambda x, y: x._delta > y._delta,
            '__ge__': lambda x, y: x._delta >= y._delta,
        }
        for op in operators:
            setattr(self.__class__, op, self._create_method(op))

    def _create_method(self, op):
        def method(self, other):
            if isinstance(other, Result):
                func = {
                    '__add__': lambda x, y: x._delta + y._delta,
                    '__sub__': lambda x, y: x._delta - y._delta,
                    '__mul__': lambda x, y: x._delta * y,
                    '__truediv__': lambda x, y: x._delta / y,
                    '__eq__': lambda x, y: x._delta == y._delta,
                    '__ne__': lambda x, y: x._delta != y._delta,
                    '__lt__': lambda x, y: x._delta < y._delta,
                    '__le__': lambda x, y: x._delta <= y._delta,
                    '__gt__': lambda x, y: x._delta > y._delta,
                    '__ge__': lambda x, y: x._delta >= y._delta,
                }[op]
                return func(self, other)
            return NotImplemented
        method.__name__ = op
        return method
