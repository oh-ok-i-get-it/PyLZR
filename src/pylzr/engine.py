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

        AudioInput → gain → FFTWorker (own thread) → AudioAnalyzer → SoundMode → output

    Displays subscribe to the signals; nothing here knows about widgets.
    Call start() to begin capturing in real time, shutdown() when done.
    tick() processes a single chunk (the real-time timer calls it).
    """

    waveform_ready      = pyqtSignal(np.ndarray)                          # gain-applied int16 chunk
    spectrum_ready      = pyqtSignal(np.ndarray, np.ndarray, np.ndarray)  # raw low/mid/high bands
    averages_ready      = pyqtSignal(float, float)                        # low_avg, high_avg per window
    modes_updated       = pyqtSignal(int, int, int, int)                  # low, high, dual-mode label, countdown
    level_measured      = pyqtSignal(float, bool)                         # peak 0–1, clipping
    diagnostics_updated = pyqtSignal(float, int)                          # FFT frames/s, I/O errors

    _process_audio = pyqtSignal(np.ndarray)

    def __init__(self, output: NoteOutput, parent: QObject | None = None):
        super().__init__(parent)
        self.bands      = BandLayout(CHUNK, SAMPLE_RATE)
        self.audio      = AudioInput(CHUNK, SAMPLE_RATE)
        self.analyzer   = AudioAnalyzer(AVG_COUNT_RATE_DEFAULT)
        self.sound_mode = SoundMode(DEFAULT_LOW_THRESHOLDS, DEFAULT_HIGH_THRESHOLDS, output)
        self._apply_dm_period(AVG_COUNT_RATE_DEFAULT)

        self.gain = 1.0              # input gain multiplier
        self.measure_level = False   # peak metering costs a little; only while someone shows it

        self._fft_frames     = 0
        self._overflow_count = 0
        self._is_shut_down   = False

        # FFT on a worker thread
        self.fft_thread = QThread(self)
        self._fft_worker = FFTWorker(self.bands)
        self._fft_worker.moveToThread(self.fft_thread)
        self.fft_thread.start()
        self._process_audio.connect(self._fft_worker.process, Qt.QueuedConnection)
        self._fft_worker.resultReady.connect(self._on_spectrum)

        self._capture_timer = QTimer(self)
        self._capture_timer.timeout.connect(self.tick)
        self._diag_timer = QTimer(self)
        self._diag_timer.timeout.connect(self._report_diagnostics)

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def start(self):
        """Capture audio in real time (one chunk per timer tick)."""
        self._capture_timer.start(self.audio.timer_interval_ms)
        self._diag_timer.start(1000)

    def stop(self):
        self._capture_timer.stop()
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
        self.sound_mode.enabled = enabled
        if enabled:
            log.info('Sound mode: ON', extra={'tone': Tone.ON})
        else:
            log.info('Sound mode: OFF', extra={'tone': Tone.OFF})

    def toggle_sound_mode(self) -> bool:
        self.set_sound_mode(not self.sound_mode.enabled)
        return self.sound_mode.enabled

    def switch_device(self, device_index: int) -> bool:
        """Switch audio input; on failure the current device keeps running."""
        was_running = self._capture_timer.isActive()
        self._capture_timer.stop()
        try:
            self.audio.switch_device(device_index)
            ok = True
        except Exception as e:
            log.error(f'Audio device switch failed: {e}')
            ok = False
        if was_running:
            self._capture_timer.start(self.audio.timer_interval_ms)
        return ok

    # ── Pipeline ───────────────────────────────────────────────────────────

    def tick(self):
        """Read one chunk and send it through the pipeline."""
        try:
            chunk = self.audio.read_chunk()
        except OSError as e:
            self._overflow_count += 1
            log.error(f'Audio I/O Error: {e}')
            return

        if self.gain != 1.0:
            chunk = np.clip(chunk.astype(np.float32) * self.gain, -32767, 32767).astype(np.int16)

        if self.measure_level:
            peak = float(np.max(np.abs(chunk))) / 32767.0
            self.level_measured.emit(peak, peak >= 0.99)

        self.waveform_ready.emit(chunk)
        self._process_audio.emit(chunk.copy())

    @pyqtSlot(np.ndarray, np.ndarray, np.ndarray)
    def _on_spectrum(self, low: np.ndarray, med: np.ndarray, high: np.ndarray):
        self._fft_frames += 1
        self.spectrum_ready.emit(low, med, high)

        result = self.analyzer.push(low.mean(), high.mean())
        if result is None:
            return
        low_avg, high_avg = result
        sm = self.sound_mode
        sm.advance_dm_counter()
        if sm.enabled:
            sm.check_mode(low_avg, high_avg)
        self.averages_ready.emit(low_avg, high_avg)
        self.modes_updated.emit(sm.low_mode, sm.high_mode, sm.dm_mode_label, sm.dm_countdown)
        log.debug(f'LOW: {low_avg:.2f}  HIGH: {high_avg:.2f}')

    def _report_diagnostics(self):
        fps, self._fft_frames = self._fft_frames, 0
        self.diagnostics_updated.emit(fps, self._overflow_count)
