import math

class Result:
    def __init__(self, seconds, wpm=265):
        self._delta = seconds
        self._wpm = wpm
        self._add_operator_methods()

    def seconds(self):
        return self._delta

    def minutes(self):
        return math.ceil(self._delta / 60)

    def text(self):
        m = self.minutes()
        if m <= 1:
            return f"{m} min read"
        return f"{m} mins read"

    def __repr__(self):
        return f"Result(seconds={self._delta}, wpm={self._wpm})"

    def __str__(self):
        return self.text()

    def _create_method(self, op):
        def method(other):
            if op == 'add':
                if isinstance(other, Result):
                    return Result(self._delta + other._delta, self._wpm)
                elif isinstance(other, (int, float)):
                    return Result(self._delta + other, self._wpm)
                else:
                    raise TypeError("Can only add Result or numeric types")
        return method

    def _add_operator_methods(self):
        # Dynamically adding __add__ as an example of operator method creation
        # based on the requirement to have _create_method and _add_operator_methods
        self.__add__ = self._create_method('add')
