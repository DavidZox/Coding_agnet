import math

class Result:
    def __init__(self, seconds, wpm=265):
        self._delta = seconds
        self._wpm = wpm
        self._add_operator_methods()

    def seconds(self):
        return self._delta

    def minutes(self):
        return self._delta / (self._wpm * 60)

    def text(self):
        minutes = math.ceil(self._delta / (self._wpm * 60))
        if minutes <= 1:
            return f"{minutes} min read"
        return f"{minutes} mins read"

    def __repr__(self):
        return f"Result(seconds={self._delta}, wpm={self._wpm})"

    def __str__(self):
        return self.text()

    def _create_method(self, op):
        def method(self, other):
            if op == 'add':
                if isinstance(other, Result):
                    return Result(self._delta + other._delta, self._wpm)
                elif isinstance(other, (int, float)):
                    return Result(self._delta + other, self._wpm)
                else:
                    raise TypeError("Operand must be Result or numeric")
            elif op == 'sub':
                if isinstance(other, Result):
                    return Result(self._delta - other._delta, self._wpm)
                elif isinstance(other, (int, float)):
                    return Result(self._delta - other, self._wpm)
                else:
                    raise TypeError("Operand must be Result or numeric")
            else:
                raise ValueError(f"Unsupported operation: {op}")
        return method

    def _add_operator_methods(self):
        # Dynamically adding addition operator method as requested by UML/Architecture
        # Note: In Python, typically we override __add__, but the spec asks for 
        # _create_method and _add_operator_methods to add methods dynamically.
        # We will implement a method named 'add' as an example of using _create_method.
        add_method = self._create_method('add')
        setattr(self, 'add', add_method)
        
        # To satisfy the requirement of "adding operator methods", 
        # we also implement the standard dunder methods using the logic.
        self.__add__ = self._create_method('add')
        
        # Adding subtraction methods as requested by the task description
        sub_method = self._create_method('sub')
        setattr(self, 'sub', sub_method)
        self.__sub__ = self._create_method('sub')
