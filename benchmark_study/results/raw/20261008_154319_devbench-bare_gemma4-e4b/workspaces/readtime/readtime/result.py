from typing import List

class Result:
    """
    Represents the calculated reading time result.
    """
    def __init__(self, seconds: float, wpm: int):
        """
        Initialize the model structure and parameters.

        :param seconds: The total estimated reading time in seconds.
        :type seconds: float
        :param wpm: The Words Per Minute rate used for calculation.
        :type wpm: int
        """
        self._seconds = seconds
        self._wpm = wpm
        self._text = f"{seconds:.2f} seconds at {wpm} WPM"

    def seconds(self) -> float:
        """
        Returns the total number of seconds in the delta.

        :return: Total reading time in seconds.
        :rtype: float
        """
        return self._seconds

    def minutes(self) -> float:
        """
        Calculates the estimated reading time in minutes.

        :return: Estimated reading time in minutes.
        :rtype: float
        """
        return self._seconds / 60.0

    def text(self) -> str:
        """
        Get the text representation of the read time.

        :return: A formatted string representing the reading time.
        :rtype: str
        """
        return self._text

    def _add_operator_methods(self):
        """
        Adds operator methods to the class dynamically (e.g., addition).
        """
        def __add__(self, other):
            if isinstance(other, Result):
                # Simple addition of seconds for demonstration
                return Result(self._seconds + other._seconds, self._wpm)
            return NotImplemented
        
        setattr(Result, '__add__', __add__)

    def _create_method(self, op: str):
        """
        Creates a method for the Result class based on the given operation.
        (Placeholder for dynamic method creation based on operation 'op')
        """
        pass

    def __repr__(self) -> str:
        """
        Return a developer-friendly representation of the object.
        """
        return f"Result(seconds={self._seconds:.2f}, wpm={self._wpm})"

    def __str__(self) -> str:
        """
        Return a user-friendly string representation of the object.
        """
        return f"Reading Time: {self.minutes():.2f} minutes ({self._seconds:.0f} seconds) at {self._wpm} WPM."

# Initialize operator methods upon class definition
Result._add_operator_methods()
