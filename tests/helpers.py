"""Test utilities: synthetic audio, event-loop waiting, and the window harness."""

import time

import numpy as np
import pyaudio as fake_pyaudio   # the fake, installed by conftest
import rtmidi as fake_rtmidi
from PyQt5.QtCore import QCoreApplication
from PyQt5.QtTest import QTest

from fakes import udp as fake_udp
from pylzr.core import CHUNK, SAMPLE_RATE


def wait_until(condition, timeout: float = 5.0):
    """Spin the Qt event loop until condition() is true (handles queued
    signals, QTimers and background threads alike)."""
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError('timed out waiting for condition')
        QCoreApplication.processEvents()
        time.sleep(0.002)


def tone_chunks(n_chunks: int, *components: tuple[float, float]) -> np.ndarray:
    """n_chunks x CHUNK int16 samples: a sum of (freq_hz, amplitude) sines.
    Deterministic — no randomness, so results are identical on every OS."""
    t = np.arange(n_chunks * CHUNK) / SAMPLE_RATE
    x = np.zeros_like(t)
    for freq, amp in components:
        x += amp * np.sin(2 * np.pi * freq * t)
    return np.clip(np.round(x), -32767, 32767).astype(np.int16).reshape(n_chunks, CHUNK)


def dmx_packets() -> list[dict]:
    """Every Art-Net packet sent through the fake network so far, decoded:
    to (host, port), sequence, sub_uni, net, data (the channel values)."""
    return [{'to': to, 'sequence': p[12], 'sub_uni': p[14], 'net': p[15], 'data': p[18:]}
            for p, to in fake_udp.sent]


def note_messages() -> list[list[int]]:
    """All MIDI messages sent so far, without port names."""
    return [msg for _, msg in fake_rtmidi.sent]


def note_ons() -> list[list[int]]:
    """[note, velocity] of every Note ON, in order. Unlike the full message
    list this is deterministic: Note OFFs arrive on a timer, so how they
    interleave with later Note ONs depends on timing."""
    return [msg[1:] for msg in note_messages() if msg[0] == 0x90]


def wait_for_note_offs():
    """Block until every Note ON sent so far has its delayed Note OFF, then
    check each OFF matches an ON (same note, velocity 0)."""
    def balanced():
        msgs = note_messages()
        return sum(m[0] == 0x90 for m in msgs) == sum(m[0] == 0x80 for m in msgs)
    wait_until(balanced)
    offs = sorted(m[1:] for m in note_messages() if m[0] == 0x80)
    assert offs == sorted([note, 0] for note, _ in note_ons())


class WindowHarness:
    """Drives a real main window with fake audio and records its output.

    This is the ONLY place the tests reach into the window's internals (its
    AudioEngine). When a refactor moves the pipeline, update this class —
    the tests that use it should not need to change.

    Recorded output:
      frames   — (low.sum, med.sum, high.sum) of every raw FFT frame's bands
      averages — (low_avg, high_avg) for every completed averaging window
    MIDI output is recorded by the fake rtmidi module (fake_rtmidi.sent).
    """

    def __init__(self, window):
        self.window = window
        self.closed = False
        self.frames: list[tuple[float, float, float]] = []
        self.averages: list[tuple[float, float]] = []

        engine = window.engine
        def record_frame(spectrum):
            low, med, high, _ = engine.bands.split(spectrum)
            self.frames.append((float(low.sum()), float(med.sum()), float(high.sum())))
        engine.spectrum_ready.connect(record_frame)
        engine.averages_ready.connect(
            lambda low_avg, high_avg: self.averages.append((float(low_avg), float(high_avg))))

    def feed(self, chunks):
        """Deliver each int16 chunk as captured audio (as PortAudio's callback
        would) and wait for its FFT frame."""
        target = len(self.frames) + len(chunks)
        for chunk in chunks:
            fake_pyaudio.deliver(np.asarray(chunk, dtype=np.int16).tobytes(),
                                 stream=self.window.engine.audio._stream)
        wait_until(lambda: len(self.frames) >= target)

    def key(self, qt_key):
        QTest.keyClick(self.window, qt_key)

    def close(self):
        """Close the window (runs its closeEvent) and schedule its deletion."""
        if self.closed:
            return
        self.closed = True
        self.window.close()
        self.window.deleteLater()
