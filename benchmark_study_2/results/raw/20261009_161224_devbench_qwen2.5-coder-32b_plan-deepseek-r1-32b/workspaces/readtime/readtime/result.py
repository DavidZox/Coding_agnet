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
        minutes = self.minutes
        if minutes < 1:
            return f"{self._delta} seconds"
        elif minutes == 1:
            return "1 minute"
        else:
            return f"{int(minutes)} minutes"

    def _add_operator_methods(self):
        operators = {
            '__add__': '+',
            '__sub__': '-',
            '__mul__': '*',
            '__truediv__': '/'
        }
        for method_name, op in operators.items():
            setattr(self, method_name, self._create_method(op))

    def _create_method(self, op):
        def method(other):
            if isinstance(other, Result):
                other_seconds = other.seconds
            elif isinstance(other, (int, float)):
                other_seconds = other
            else:
                raise TypeError(f"Unsupported operand type(s) for {op}: 'Result' and {type(other).__name__}")
            new_seconds = eval(f"{self._delta} {op} other_seconds")
            return Result(new_seconds, self._wpm)
        return method
