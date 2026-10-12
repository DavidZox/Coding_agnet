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
        if self.minutes >= 1:
            return f"{self.minutes:.2f} minutes"
        else:
            return f"{self.seconds} seconds"

    def _add_operator_methods(self):
        operators = {
            '__add__': lambda other: self.seconds + other.seconds,
            '__sub__': lambda other: self.seconds - other.seconds,
            '__mul__': lambda other: self.seconds * other,
            '__truediv__': lambda other: self.seconds / other,
            '__eq__': lambda other: self.seconds == other.seconds,
            '__ne__': lambda other: self.seconds != other.seconds,
            '__lt__': lambda other: self.seconds < other.seconds,
            '__le__': lambda other: self.seconds <= other.seconds,
            '__gt__': lambda other: self.seconds > other.seconds,
            '__ge__': lambda other: self.seconds >= other.seconds
        }
        for op, func in operators.items():
            self._create_method(op, func)

    def _create_method(self, op):
        def method(other):
            if isinstance(other, Result):
                return Result(self._delta + other._delta, self._wpm)
            return Result(self._delta + other, self._wpm)
        setattr(self.__class__, op, method)
