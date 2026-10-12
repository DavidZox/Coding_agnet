import math

class Result:
    def __init__(self, seconds, wpm=265):
        self._seconds = seconds
        self._wpm = wpm
        self._add_operator_methods()

    @property
    def seconds(self):
        return self._seconds

    @property
    def minutes(self):
        return math.ceil(self._seconds / 60)

    @property
    def text(self):
        m = self.minutes
        if m == 1:
            return "1 min"
        return f"{m} min"

    def __repr__(self):
        return f"Result(seconds={self._seconds}, wpm={self._wpm})"

    def __str__(self):
        return self.text

    def _create_method(self, op):
        def method(self, other):
            if isinstance(other, Result):
                return Result(self._seconds + other._seconds, self._wpm)
            elif isinstance(other, (int, float)):
                return Result(self._seconds + other, self._wpm)
            else:
                raise TypeError(f"Cannot add {type(other)} to Result")
        return method

    def _add_operator_methods(self):
        # Dynamically adding __add__ for the purpose of the requirement
        # Although the prompt asks for _create_method and _add_operator_methods,
        # it implies these are used to implement operator overloading.
        self.__add__ = self._create_method('add')
