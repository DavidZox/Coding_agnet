class Result:
    def __init__(self, seconds, wpm):
        self.delta = seconds
        self.wpm = wpm
        self._add_operator_methods()

    def __repr__(self):
        return f"Result(seconds={self.seconds}, wpm={self.wpm})"

    def __str__(self):
        return self.text()

    @property
    def seconds(self):
        return self.delta

    @property
    def minutes(self):
        return self.seconds / 60

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
            '__ge__': lambda other: self.seconds >= other.seconds,
        }
        for op, func in operators.items():
            setattr(self, op, self._create_method(op, func))

    def _create_method(self, op, func):
        def method(other):
            if isinstance(other, Result):
                return Result(func(other), self.wpm)
            elif isinstance(other, (int, float)):
                return Result(func(other), self.wpm)
            else:
                return NotImplemented
        return method
