class AudioAnalyzer:
    """Accumulates per-frame spectrum means and emits windowed averages.

    Call push() each frame. When count_rate frames have been collected,
    push() returns (low_avg, high_avg) and resets; otherwise returns None.
    """

    def __init__(self, count_rate: int):
        self.count_rate = count_rate

    @property
    def count_rate(self) -> int:
        return self._count_rate

    @count_rate.setter
    def count_rate(self, val: int):
        """Changing the window size discards the partially filled window."""
        self._count_rate = val
        self._low_scale  = 1000.0  / val
        self._high_scale = 10000.0 / val
        self._reset()

    def _reset(self):
        # Start from int 0 like sum(), so totals accumulate in the same order
        # and precision as summing the stored values would
        self._frames   = 0
        self._low_sum  = 0
        self._high_sum = 0

    def push(self, low_mean: float, high_mean: float):
        """Returns (low_avg, high_avg) when window is full, else None."""
        self._low_sum  += low_mean
        self._high_sum += high_mean
        self._frames   += 1
        if self._frames >= self._count_rate:
            result = (self._low_sum * self._low_scale, self._high_sum * self._high_scale)
            self._reset()
            return result
        return None
