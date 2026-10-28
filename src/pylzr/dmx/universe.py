from collections.abc import Sequence

from ..core import DMX_CHANNELS


class DMXUniverse:
    """The 512 channel values of one DMX universe. Pure data: no I/O, no Qt.

    Channels are numbered 1–512, as in fixture manuals; values are 0–255.
    Two layers make up what is sent:

      base       set by the show (scenes, mappings — later phases)
      overrides  manual values (the channel tester) that win over the base
                 until cleared, without changing it

    frame() is the merged result, ready for build_artdmx().
    """

    def __init__(self):
        self._base = bytearray(DMX_CHANNELS)
        self._overrides: dict[int, int] = {}     # 0-based index -> value

    @staticmethod
    def _span(start: int, values: Sequence[int]) -> tuple[int, bytes]:
        """Validate channels start … start+len-1 and values; returns
        (0-based index, values as bytes)."""
        if isinstance(values, int):              # bytes(5) would mean five zeros
            raise TypeError('values must be a sequence of ints, not an int')
        data = bytes(values)                     # ValueError unless every value is 0–255
        if not (isinstance(start, int) and 1 <= start and start + len(data) - 1 <= DMX_CHANNELS):
            raise ValueError(f'channels {start}–{start + len(data) - 1} are outside 1–{DMX_CHANNELS}')
        return start - 1, data

    # ── Base layer ──────────────────────────────────────────────────────

    def get(self, channel: int) -> int:
        """Base value of `channel` (overrides not applied)."""
        index, _ = self._span(channel, [0])
        return self._base[index]

    def set(self, channel: int, value: int):
        self.set_range(channel, [value])

    def set_range(self, start: int, values: Sequence[int]):
        """Set consecutive channels from `start`."""
        index, data = self._span(start, values)
        self._base[index:index + len(data)] = data

    def clear(self):
        """Every base channel to 0 (overrides are kept)."""
        self._base[:] = bytes(DMX_CHANNELS)

    # ── Override layer ──────────────────────────────────────────────────

    def set_overrides(self, start: int, values: Sequence[int]):
        """Override channels start … start+len-1, replacing any previous
        overrides (so channels no longer listed go back to the base)."""
        index, data = self._span(start, values)
        self._overrides = {index + i: value for i, value in enumerate(data)}

    def clear_overrides(self):
        self._overrides = {}

    @property
    def has_overrides(self) -> bool:
        return bool(self._overrides)

    # ── Output ──────────────────────────────────────────────────────────

    def frame(self) -> bytes:
        """All 512 values, channel 1 first, with overrides applied."""
        merged = bytearray(self._base)
        for index, value in self._overrides.items():
            merged[index] = value
        return bytes(merged)
