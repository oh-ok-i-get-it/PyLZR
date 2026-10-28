import math

import numpy as np
from PyQt5.QtCore import QObject, QThread, QTimer, Qt, pyqtSignal, pyqtSlot

from .analysis import AudioAnalyzer, BandLayout, FFTWorker, SoundMode
from .audio import AudioInput
from .core import (
    AVG_COUNT_RATE_DEFAULT, CHUNK, DEFAULT_HIGH_THRESHOLDS, DEFAULT_LOW_THRESHOLDS,
    DM_TOGGLE_FRAMES, SAMPLE_RATE,
)
from .core.app_logger import Tone, get_logger
from .core.protocols import NoteOutput

log = get_logger('engine')


class AudioEngine(QObject):
    """The sound-reactive pipeline, independent of any GUI:

        AudioInput (PortAudio thread) → gain → FFTWorker (own thread)
            → AudioAnalyzer → SoundMode → output

    Captured chunks are queued onto this object's (GUI) thread in arrival
    order, so a busy GUI delays processing instead of losing audio.
    Displays subscribe to the signals; nothing here knows about widgets.
    Call start() to begin capturing, shutdown() when done.
    """

    waveform_ready      = pyqtSignal(np.ndarray)                          # gain-applied int16 chunk
    spectrum_ready      = pyqtSignal(np.ndarray)                          # raw scaled spectrum (see BandLayout)
    averages_ready      = pyqtSignal(float, float)                        # low_avg, high_avg per window
    modes_updated       = pyqtSignal(int, int, int, int)                  # low, high, dual-mode label, countdown
    level_measured      = pyqtSignal(float, bool)                         # peak 0–1, clipping
    diagnostics_updated = pyqtSignal(float, int)                          # FFT frames/s, input overflows

    _chunk_captured = pyqtSignal(np.ndarray, bool)   # from PortAudio's thread
    _process_audio  = pyqtSignal(np.ndarray)

    def __init__(self, output: NoteOutput, parent: QObject | None = None,
                 device_name: str | None = None):
        """device_name: preferred audio input (falls back to the system default)."""
        super().__init__(parent)
        self.bands      = BandLayout(CHUNK, SAMPLE_RATE)
        self.audio      = AudioInput(CHUNK, SAMPLE_RATE, on_chunk=self._chunk_captured.emit,
                                     device_name=device_name)
        self.analyzer   = AudioAnalyzer(AVG_COUNT_RATE_DEFAULT)
        self.sound_mode = SoundMode(DEFAULT_LOW_THRESHOLDS, DEFAULT_HIGH_THRESHOLDS, output)
        self._apply_dm_period(AVG_COUNT_RATE_DEFAULT)

        self.gain = 1.0              # input gain multiplier
        self.measure_level = False   # peak metering costs a little; only while someone shows it

        self._last_averages: tuple[float, float] | None = None
        self._fft_frames       = 0
        self._overflow_count   = 0      # total since start (shown in Settings)
        self._recent_overflows = 0      # since the last diagnostics report
        self._is_shut_down     = False

        # FFT on a worker thread
        self.fft_thread = QThread(self)
        self._fft_worker = FFTWorker(self.bands)
        self._fft_worker.moveToThread(self.fft_thread)
        self.fft_thread.start()
        self._process_audio.connect(self._fft_worker.process, Qt.QueuedConnection)
        self._fft_worker.resultReady.connect(self._on_spectrum)

        self._chunk_captured.connect(self._process_chunk, Qt.QueuedConnection)

        self._diag_timer = QTimer(self)
        self._diag_timer.timeout.connect(self._report_diagnostics)

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def start(self):
        """Start capturing audio."""
        self.audio.start()
        self._diag_timer.start(1000)

    def stop(self):
        self.audio.stop()
        self._diag_timer.stop()

    def shutdown(self):
        """Stop capturing and release audio and the FFT thread. Safe to call twice."""
        if self._is_shut_down:
            return
        self._is_shut_down = True
        self.stop()
        self.audio.close()
        self.fft_thread.quit()
        self.fft_thread.wait()

    # ── Settings ───────────────────────────────────────────────────────────

    def set_gain(self, gain: float):
        self.gain = gain

    def set_count_rate(self, frames: int):
        """Frames per averaging window. Also rescales the dual-mode period so
        it stays DM_TOGGLE_FRAMES long."""
        self.analyzer.count_rate = frames
        self._apply_dm_period(frames)

    def _apply_dm_period(self, count_rate: int):
        # Whole windows until the flip (ceil: the flip happens once the
        # counter reaches DM_TOGGLE_FRAMES / count_rate)
        self.sound_mode.set_dm_toggle_rate(math.ceil(DM_TOGGLE_FRAMES / count_rate))

    def set_fft_window(self, name: str):
        # set_window runs directly — a single-frame transition artefact is imperceptible
        self._fft_worker.set_window(name)
        log.info(f'FFT window: {name}', extra={'tone': Tone.MUTED})

    def set_sound_mode(self, enabled: bool):
        """Turning sound mode on sends the cue for the current audio straight
        away (from the latest window), replacing any manual keyboard cue."""
        sm = self.sound_mode
        sm.enabled = enabled
        if not enabled:
            log.info('Sound mode: OFF', extra={'tone': Tone.OFF})
            return
        log.info('Sound mode: ON', extra={'tone': Tone.ON})
        sm.reset()
        if self._last_averages is not None:
            sm.check_mode(*self._last_averages)
            self.modes_updated.emit(sm.low_mode, sm.high_mode, sm.dm_mode_label, sm.dm_countdown)

    def toggle_sound_mode(self) -> bool:
        self.set_sound_mode(not self.sound_mode.enabled)
        return self.sound_mode.enabled

    def switch_device(self, device_index: int | None) -> bool:
        """Switch audio input (None = system default); on failure the current
        device keeps running."""
        try:
            self.audio.switch_device(device_index)
            return True
        except Exception as e:
            log.error(f'Audio device switch failed: {e}')
            return False

    def refresh_devices(self) -> bool:
        """Rescan audio inputs (restarts PortAudio; capture pauses briefly)."""
        try:
            self.audio.refresh_devices()
            return True
        except Exception as e:
            log.error(f'Audio device rescan failed: {e}')
            return False

    # ── Pipeline ───────────────────────────────────────────────────────────

    @pyqtSlot(np.ndarray, bool)
    def _process_chunk(self, chunk: np.ndarray, overflowed: bool):
        """One captured chunk, on the GUI thread."""
        if overflowed:
            self._overflow_count   += 1
            self._recent_overflows += 1

        if self.gain != 1.0:
            chunk = np.clip(chunk.astype(np.float32) * self.gain, -32767, 32767).astype(np.int16)

        if self.measure_level:
            peak = float(np.max(np.abs(chunk))) / 32767.0
            self.level_measured.emit(peak, peak >= 0.99)

        self.waveform_ready.emit(chunk)
        self._process_audio.emit(chunk)

    @pyqtSlot(np.ndarray)
    def _on_spectrum(self, spectrum: np.ndarray):
        self._fft_frames += 1
        self.spectrum_ready.emit(spectrum)

        low, _, high, _ = self.bands.split(spectrum)
        result = self.analyzer.push(low.mean(), high.mean())
        if result is None:
            return
        low_avg, high_avg = result
        self._last_averages = result
        sm = self.sound_mode
        sm.advance_dm_counter()
        if sm.enabled:
            sm.check_mode(low_avg, high_avg)
        self.averages_ready.emit(low_avg, high_avg)
        self.modes_updated.emit(sm.low_mode, sm.high_mode, sm.dm_mode_label, sm.dm_countdown)
        log.debug(f'LOW: {low_avg:.2f}  HIGH: {high_avg:.2f}')

    def _report_diagnostics(self):
        fps, self._fft_frames = self._fft_frames, 0
        if self._recent_overflows:
            log.warning(f'Audio input overflowed {self._recent_overflows}× in the last second')
            self._recent_overflows = 0
        self.diagnostics_updated.emit(fps, self._overflow_count)
