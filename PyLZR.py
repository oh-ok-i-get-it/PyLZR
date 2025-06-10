import sys
import numpy as np
import pyqtgraph as pg
import pyaudio
from scipy.fftpack import rfft
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QSlider
from PyQt5.QtGui import QKeyEvent
from PyQt5.QtCore import QTimer, Qt

import textClass as txt
import Qtmidi as midi
import soundModeClass as sm


class PyLZR(QWidget):
    def __init__(self):
        super().__init__()

        # — SM & Dual-Mode setup —
        self.LOW_QUIET_MODE_CUTOFF   = 90
        self.LOW_MODE1_CUTOFF        = 180
        self.LOW_MODE2_CUTOFF        = 200

        self.HIGH_QUIET_MODE_CUTOFF  = 10
        self.HIGH_MODE1_CUTOFF       = 180
        self.HIGH_MODE2_CUTOFF       = 200

        self.DM_TIME_RATE = 2400
        self.dm_count     = 0

        # — Audio & plotting setup —
        self.init_audio()
        self.init_plot()
        self.init_ui()

        # Now that count_rate is known:
        self.dm_rate     = self.DM_TIME_RATE / self.count_rate
        self._low_scale  = 1000.0  / self.count_rate
        self._high_scale = 10000.0 / self.count_rate

        # — MIDI & SoundMode —
        self.vm = midi.VirtualMIDI()
        self.soundmode = sm.SoundMode(
            self.LOW_QUIET_MODE_CUTOFF,
            self.LOW_MODE1_CUTOFF,
            self.LOW_MODE2_CUTOFF,
            self.HIGH_QUIET_MODE_CUTOFF,
            self.HIGH_MODE1_CUTOFF,
            self.HIGH_MODE2_CUTOFF,
            self.vm
        )

        # — SM accumulators & counters —
        self._low_acc   = 0.0
        self._high_acc  = 0.0
        self._frame_cnt = 0

        # — Timer for update loop —
        self.timer = QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(self.audio_rate)

    def init_audio(self):
        # Spectrum-averaging params
        self.count_rate = 20
        self.low_avg    = 0.0
        self.high_avg   = 0.0

        # Preallocate waveform buffer
        self.CHUNK   = 1024 * 2
        self.wf_data = np.empty(self.CHUNK, dtype=np.int16)

        # rfft output length = CHUNK/2+1
        self.LOW_C_CUTOFF  = self.CHUNK // 128
        self.MED_C_CUTOFF  = self.CHUNK // 4
        self.ALL_C_CUTOFF  = self.CHUNK // 2 + 1

        self._sp_scale = 2.0 / (128.0 * self.CHUNK)

        p = pyaudio.PyAudio()
        self.stream = p.open(
            format    = pyaudio.paInt16,
            channels  = 1,
            rate      = 44100,
            input     = True,
            output    = True,
            frames_per_buffer = self.CHUNK
        )

        # Precompute the frequency axes
        self.x      = np.arange(0, 2*self.CHUNK, 2)
        self.f_low  = np.linspace(0, 44100/128, self.LOW_C_CUTOFF)
        self.f_med  = np.linspace(44100/128, 44100/4,
                                  self.MED_C_CUTOFF - self.LOW_C_CUTOFF)
        self.f_high = np.linspace(44100/4, 44100/2,
                                  self.ALL_C_CUTOFF - self.MED_C_CUTOFF)

        self.audio_rate = 10  # ms between frames

    def init_plot(self):
        self.plot_widget = pg.GraphicsLayoutWidget()
        self.plot_widget.resize(1000, 600)
        pg.setConfigOptions(antialias=True)

        # Waveform
        wf_x = pg.AxisItem(orientation='bottom')
        wf_x.setTicks([[(0,'0'),(1024,'1024'),(2048,'2048'),
                        (3072,'3072'),(4096,'4096')]])
        self.waveform = self.plot_widget.addPlot(
            title="WAVEFORM", row=1, col=1, axisItems={'bottom': wf_x}
        )
        self.waveform.setYRange(0,255, padding=0)
        self.waveform.setXRange(0,2*self.CHUNK, padding=0.005)

        # Spectrum
        sp_x = pg.AxisItem(orientation='bottom')
        sp_x.setTicks([[ 
            (np.log10(10),'10Hz'), (np.log10(100),'100Hz'),
            (np.log10(250),'250Hz'),(np.log10(400),'400Hz'),
            (np.log10(1000),'1kHz'),(np.log10(22050),'22kHz')
        ]])
        self.spectrum = self.plot_widget.addPlot(
            title="SPECTRUM", row=2, col=1, axisItems={'bottom': sp_x}
        )
        self.spectrum.setLogMode(x=True, y=True)
        self.spectrum.setYRange(-4,0, padding=0)
        self.spectrum.setXRange(np.log10(20), np.log10(44100/2), padding=0.005)

        self.traces = {}

    def init_ui(self):
        self.setWindowTitle('PyLZR : SSP3CTRUM')
        self.setGeometry(100,100,1200,800)

        self.count_slider = QSlider(Qt.Horizontal, self)
        self.count_slider.setRange(10,50)
        self.count_slider.setValue(self.count_rate)
        self.count_slider.setTickInterval(5)
        self.count_slider.setTickPosition(QSlider.TicksBelow)
        self.count_slider.valueChanged.connect(self._on_count_rate_change)

        self.count_label = QLabel(f"Avgs Calc Rate: {self.count_rate}", self)
        self.key_label   = QLabel('Press any key', self)

        layout = QVBoxLayout()
        layout.addWidget(self.count_slider)
        layout.addWidget(self.count_label)
        layout.addWidget(self.key_label)
        layout.addWidget(self.plot_widget)
        self.setLayout(layout)

    def _on_count_rate_change(self, val):
        self.count_rate = val
        self.count_label.setText(f"Avgs Calc Rate: {val}")
        self.dm_rate     = self.DM_TIME_RATE / val
        self._low_scale  = 1000.0  / val
        self._high_scale = 10000.0 / val

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        self.vm.keyboard(key)
        self.key_label.setText(f"Key: {event.text()} (code {key})")
        super().keyPressEvent(event)

    def update(self):
        try:
            raw = self.stream.read(self.CHUNK, exception_on_overflow=False)
            audio = np.frombuffer(raw, dtype=np.int16)
            self.wf_data[:] = audio + 127

            # waveform
            if 'waveform' not in self.traces:
                self.traces['waveform'] = self.waveform.plot(pen='c', width=3)
            self.traces['waveform'].setData(self.x, self.wf_data)

            # spectrum
            sp = np.abs(rfft(self.wf_data - 128)) * self._sp_scale

            low  = sp[:self.LOW_C_CUTOFF]
            med  = sp[self.LOW_C_CUTOFF:self.MED_C_CUTOFF]
            high = sp[self.MED_C_CUTOFF:self.ALL_C_CUTOFF]

            # store for run_sm()
            self.sp_data_low  = low
            self.sp_data_high = high

            # batch‐update plots
            for name,data,axis in (
                ('spectrum_low',  low,  self.f_low),
                ('spectrum_med',  med,  self.f_med),
                ('spectrum_high', high, self.f_high),
            ):
                if name not in self.traces:
                    pen = {'spectrum_low':'y',
                           'spectrum_med':'b',
                           'spectrum_high':'m'}[name]
                    self.traces[name] = self.spectrum.plot(pen=pen, width=3)
                self.traces[name].setData(axis, data)

            self.key_label.setText(
                f"Low Avg: {self.low_avg:.6f} | High Avg: {self.high_avg:.6f}"
            )

            self.run_sm()

        except IOError as e:
            print(f"Audio I/O Error: {e}")

    def run_sm(self):
        # use the spectral slices now stored on self
        low_mean  = self.sp_data_low.mean()
        high_mean = self.sp_data_high.mean()

        self._low_acc   += low_mean
        self._high_acc  += high_mean
        self._frame_cnt += 1

        if self._frame_cnt >= self.count_rate:
            self.low_avg   = self._low_acc  * self._low_scale
            self.high_avg  = self._high_acc * self._high_scale
            self._low_acc   = 0.0
            self._high_acc  = 0.0
            self._frame_cnt = 0

            # dual-mode toggle
            self.dm_count += 1
            if self.dm_count >= self.dm_rate:
                self.dm_count = 0
                self.soundmode.toggle_dm_mode()

            if self.vm.sm_ON:
                self.soundmode.check_mode(self.low_avg, self.high_avg)

            # console output
            print(
                f"{txt.YELLOW}{txt.I}LOW: {txt.IOFF}{txt.B}"
                f"{self.low_avg:.2f}{txt.BOFF}\t"
                f"{txt.PURPLE}{txt.I}HIGH: {txt.IOFF}{txt.B}"
                f"{self.high_avg:.2f}{txt.BOFF}"
            )
            print(f"DM COUNT: {self.dm_count}   DM RATE: {self.dm_rate}")
            print(f"DM ON?: {self.soundmode.get_dm_mode_bool()}")


if __name__ == '__main__':
    app    = QApplication(sys.argv)
    window = PyLZR()
    window.show()
    sys.exit(app.exec_())
