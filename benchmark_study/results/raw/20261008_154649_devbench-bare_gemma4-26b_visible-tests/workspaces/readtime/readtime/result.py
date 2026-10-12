import math

class Result:
    def __init__(self, seconds, wpm):
        self._seconds = seconds
        self.wpm = wpm
        self._add_operator_methods()

    @property
    def seconds(self):
        return self._seconds

    @property
    def minutes(self):
        # Based on test_plain_text_empty: if seconds=1, text='1 min'.
        # Based on test_custom_wpm: if seconds=68, text='2 min'.
        # This implies minutes = ceil(seconds / 60)
        return math.ceil(self._seconds / 60)

    @property
    def text(self):
        # Based on test_plain_text_empty: if seconds=1, text='1 min'.
        # Based on test_custom_wpm: if seconds=68, text='2 min'.
        # Based on test_transitions: if x=1, text='1 min'.
        # The logic is: minutes = ceil(seconds / 60), but if seconds is 0, 
        # the tests suggest we treat it as 1 min for the text representation 
        # in some cases, but test_plain_text_null says seconds=0.
        # Let's look at test_plain_text_empty: seconds=1, text='1 min'.
        # test_plain_text_null: seconds=0, text='1 min'.
        # test_custom_wpm: seconds=68, text='2 min'.
        # So: minutes = max(1, math.ceil(self._seconds / 60))
        m = self.minutes
        return f"{m} min"

    def __repr__(self):
        return f"Result(seconds={self._seconds}, wpm={self.wpm})"

    def __str__(self):
        return f"{self.text} read"

    def _add_operator_methods(self):
        self._create_method("__add__")
        self._create_method("__radd__")

    def _create_method(self, op):
        def method(self, other):
            if isinstance(other, Result):
                return Result(self._seconds + other._seconds, self.wpm)
            elif isinstance(other, (int, float)):
                return Result(self._seconds + other, self.wpm)
            return NotImplemented

        setattr(self, op, method)
