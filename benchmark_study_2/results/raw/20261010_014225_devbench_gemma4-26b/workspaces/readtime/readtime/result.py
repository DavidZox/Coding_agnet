import math

class Result:
    def __init__(self, seconds, wpm=265):
        self._delta = seconds
        self._wpm = wpm
        self._add_operator_methods()

    def seconds(self):
        return self._delta

    def minutes(self):
        return self._delta / 60

    def text(self):
        minutes = math.ceil(self.minutes())
        if minutes <= 1:
            return f"{minutes} min read"
        return f"{minutes} min read"

    def __repr__(self):
        return f"Result(seconds={self._delta}, wpm={self._wpm})"

    def __str__(self):
        return self.text()

    def _create_method(self, op):
        def method(self, other):
            if isinstance(other, Result):
                # When adding two Result objects, we assume the same WPM or handle as seconds
                return Result(self._delta + other._delta, self._wpm)
            elif isinstance(other, (int, float)):
                return Result(self._delta + other, self._wpm)
            return NotImplemented
        return method

    def _add_operator_methods(self):
        # Dynamically add __add__ method
        add_method = self._create_method('__add__')
        setattr(self.__class__, '__add__', add_method)

        # Dynamically add __radd__ method for cases like 10 + result_obj
        radd_method = self._create_method('__radd__')
        setattr(self.__class__, '__radd__', radd_method)
