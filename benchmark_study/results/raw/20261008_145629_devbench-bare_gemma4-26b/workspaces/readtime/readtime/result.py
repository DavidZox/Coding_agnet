class Result:
    def __init__(self, seconds, wpm):
        self._delta = seconds
        self._wpm = wpm
        self._add_operator_methods()

    @property
    def seconds(self):
        return self._delta

    @property
    def minutes(self):
        return self._delta / 60.0

    @property
    def text(self):
        minutes = int(self.minutes)
        if minutes < 1:
            return "Less than a minute"
        if minutes == 1:
            return "1 minute"
        return f"{minutes} minutes"

    def _create_method(self, op):
        def method(self, other):
            if isinstance(other, Result):
                return Result(self._delta + other._delta, self._wpm)
            elif isinstance(other, (int, float)):
                return Result(self._delta + other, self._wpm)
            else:
                raise TypeError("Operand must be Result, int, or float")
        return method

    def _add_operator_methods(self):
        self.__add__ = self._create_method(lambda s, o: s + o)
        self.__radd__ = self._create_method(lambda s, o: s + o)

    def __repr__(self):
        return f"Result(seconds={self._delta}, wpm={self._wpm})"

    def __str__(self):
        return self.text
