class Result:
    """
    Represents the calculated reading time.
    """
    def __init__(self, seconds: int, wpm: int):
        """
        Initializes the Result object.

        :param seconds: The total reading time in seconds.
        :param wpm: The words per minute rate used for calculation.
        """
        self._seconds = seconds
        self._wpm = wpm
        self._add_operator_methods()

    def seconds(self) -> int:
        """
        Returns the total number of seconds.
        """
        return self._seconds

    def minutes(self) -> float:
        """
        Calculates the estimated reading time in minutes.
        """
        return self._seconds / 60.0

    def text(self) -> str:
        """
        Returns the text representation of the read time (e.g., 'X minutes Y seconds').
        """
        total_minutes = int(self.minutes())
        remaining_seconds = self._seconds % 60
        
        parts = []
        if total_minutes > 0:
            parts.append(f"{total_minutes} minute{'s' if total_minutes != 1 else ''}")
        if remaining_seconds > 0 or total_minutes == 0:
            parts.append(f"{remaining_seconds} second{'s' if remaining_seconds != 1 else ''}")
            
        if not parts:
            return "0 seconds"
            
        return ", ".join(parts)

    def _add_operator_methods(self):
        """
        Adds operator methods to the class dynamically.
        """
        self._create_method("+")
        self._create_method("-")
        self._create_method("*")
        self._create_method("/")

    def _create_method(self, op: str):
        """
        Creates a method for the Result class based on the given operation.
        """
        def method_factory(operation):
            def method(other):
                if not isinstance(other, Result):
                    raise TypeError("Unsupported operand type(s) for {}.".format(operation))
                
                if operation == '+':
                    return Result(self._seconds + other._seconds, self._wpm)
                elif operation == '-':
                    return Result(self._seconds - other._seconds, self._wpm)
                elif operation == '*':
                    # Assuming multiplication relates to scaling time, though context is vague, 
                    # we'll treat it as scaling seconds for simplicity based on typical object math.
                    return Result(int(self._seconds * other._seconds / 100), self._wpm) 
                elif operation == '/':
                    # Division might represent ratio, but for time, we'll treat it as division of seconds
                    if other._seconds == 0:
                        raise ZeroDivisionError("Cannot divide by zero seconds.")
                    return Result(int(self._seconds / other._seconds * 100), self._wpm)
                else:
                    raise NotImplementedError(f"Operation {operation} not implemented.")
            return method

        setattr(self, op, method_factory(op))

    def __repr__(self) -> str:
        return f"Result(seconds={self._seconds}, wpm={self._wpm})"

    def __str__(self) -> str:
        return self.text()
