import math

class Result:
    def __init__(self, seconds, wpm=265):
        self._delta = seconds
        self.wpm = wpm
        self._add_operator_methods()

    @property
    def seconds(self):
        return self._delta

    @property
    def minutes(self):
        return math.ceil(self._delta / 60)

    def text(self):
        minutes = self.minutes
        if minutes <= 1:
            return f"{minutes} min read"
        return f"{minutes} min read"

    def __repr__(self):
        return f"Result(seconds={self._delta}, wpm={self.wpm})"

    def __str__(self):
        return self.text()

    def _create_method(self, op):
        def method(other):
            if isinstance(other, Result):
                return Result(self._delta + other._delta, self.wpm)
            elif isinstance(other, (int, float)):
                return Result(self._delta + other, self.wpm)
            else:
                raise TypeError(f"Cannot add {type(other)} to Result")
        return method

    def _add_operator_methods(self):
        # Dynamically adding basic arithmetic operators as requested by the design
        # Although the UML doesn't specify which ones, the architecture mentions _create_method(op)
        # We implement __add__ as a primary example of dynamic method creation
        self.__add__ = self._create_method('add')
        # In a real dynamic scenario, one might use setattr, but here we follow the requirement
        # to have these methods exist via the internal logic.
        
        # To strictly follow "adds operator methods to the class dynamically"
        # we can use setattr on the class or instance.
        setattr(self, '__add__', self._create_method('add'))
