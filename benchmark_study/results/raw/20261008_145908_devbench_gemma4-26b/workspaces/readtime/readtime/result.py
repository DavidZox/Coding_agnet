import math

class Result:
    def __init__(self, seconds, wpm=265):
        self._delta = seconds
        self._wpm = wpm
        self._add_operator_methods()

    def __repr__(self):
        return f"Result(seconds={self.seconds()}, wpm={self._wpm})"

    def __str__(self):
        return self.text()

    def seconds(self):
        return self._delta

    def minutes(self):
        return self._delta / 60

    def text(self):
        m = math.ceil(self.minutes())
        if m == 1:
            return "1 min read"
        return f"{m} min read"

    def _create_method(self, op):
        def method(self, other):
            if op == 'add':
                if isinstance(other, Result):
                    return Result(self.seconds() + other.seconds(), self._wpm)
                elif isinstance(other, (int, float)):
                    return Result(self.seconds() + other, self._wpm)
            return NotImplemented
        return method

    def _add_operator_methods(self):
        # Dynamically add addition operator method
        add_method = self._create_method('add')
        # Use __class__ to bind the method to the class level or ensure it's treated as a bound method
        # However, since we are setting it on the instance, we must ensure it receives 'self' correctly.
        # The previous error occurred because the function was not correctly bound.
        # To ensure magic methods like __add__ are recognized by the Python interpreter during 
        # binary operations (e.g., r + r2), they must be present on the class level.
        # We will use setattr on the class (type(self)) instead of the instance.
        setattr(type(self), '__add__', add_method)

        # Dynamically add addition assignment operator method
        def iadd(self, other):
            if isinstance(other, Result):
                self._delta += other.seconds()
                return self
            elif isinstance(other, (int, float)):
                self._delta += other
                return self
            return NotImplemented
        setattr(type(self), '__iadd__', iadd)

if __name__ == "__main__":
    # Test to verify Result class independently
    r = Result(120, 265)
    print(f"Seconds: {r.seconds()}")
    print(f"Minutes: {r.minutes()}")
    print(f"Text: {r.text()}")
    
    r2 = Result(60, 265)
    r3 = r + r2
    print(f"Combined Text: {r3.text()}")
