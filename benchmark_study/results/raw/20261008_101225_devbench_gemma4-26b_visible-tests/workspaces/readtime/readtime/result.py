import math

class Result:
    def __init__(self, seconds, wpm=265):
        self._delta = seconds
        self._wpm = wpm
        self.wpm = wpm
        self._add_operator_methods()

    @property
    def seconds(self):
        return max(1, round(self._delta))

    @property
    def minutes(self):
        return self._delta / 60

    @property
    def text(self):
        minutes = math.ceil(self.minutes)
        return f"{minutes} min read"

    def _create_method(self, op):
        def method(self, other):
            if not isinstance(other, Result):
                raise TypeError(f"Can only {op[4:]} Result to Result")
            
            if op == '__add__':
                return Result(self.seconds + other.seconds, self._wpm)
            elif op == '__sub__':
                return Result(self.seconds - other.seconds, self._wpm)
            elif op == '__mul__':
                return Result(self.seconds * other.seconds, self._wpm)
            elif op == '__truediv__':
                return Result(self.seconds / other.seconds, self._wpm)
            else:
                raise NotImplementedError(f"Operation {op} not implemented")
        return method

    def _add_operator_methods(self):
        self.__add__ = self._create_method('__add__')
        self.__sub__ = self._create_method('__sub__')
        self.__mul__ = self._create_method('__mul__')
        self.__truediv__ = self._create_method('__truediv__')

    def __repr__(self):
        return f"Result(seconds={self.seconds}, wpm={self._wpm})"

    def __str__(self):
        return self.text
