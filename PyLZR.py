import sys
import numpy as np
import pyqtgraph as pg
import pyaudio
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QSlider
from PyQt5.QtGui import QKeyEvent
from PyQt5.QtCore import QTimer, Qt, QThread, pyqtSignal, pyqtSlot, QSignalBlocker
from scipy.fftpack import rfft
from collections import deque

import textClass as txt
import Qtmidi as midi
import soundModeClass as sm
from fftWorker import FFTWorker

# Cutoff Sliders Max Value
CUTOFF_SLIDER_MAX = 10_000

class PyLZR(QWidget):
    processAudio = pyqtSignal(np.ndarray)

    def __init__(self):
        super().__init__()

        # — SM & Dual-Mode setup —
        self.LOW_QUIET_MODE_CUTOFF   = 100
        self.LOW_MODE1_CUTOFF        = 300
        self.LOW_MODE2_CUTOFF        = 500
        self.HIGH_QUIET_MODE_CUTOFF  = 100
        self.HIGH_MODE1_CUTOFF       = 300
        self.HIGH_MODE2_CUTOFF       = 500
        
        self.DM_TIME_RATE = 2400
        self.dm_count     = 0

        # — Audio & plotting setup —
        self.init_audio()
        self.init_plot()
        self.init_ui()

        # — SM block accumulation using deque —
        self._low_means = deque()
        self._high_means = deque()
        # Precompute per-block scale factors
        self._low_scale = 1000.0 / self.count_rate
        self._high_scale = 10000.0 / self.count_rate

        # derived DM-toggle rate
        self.dm_rate = self.DM_TIME_RATE / self.count_rate
        self.low_avg = 0.0
        self.high_avg = 0.0

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

        # — FFT worker thread —
        self.fft_thread = QThread(self)
        self.fft_worker = FFTWorker(
            sp_scale=self._sp_scale,
            lo_cut=self.LOW_C_CUTOFF,
            med_cut=self.MED_C_CUTOFF,
            hi_cut=self.ALL_C_CUTOFF
        )
        self.fft_worker.moveToThread(self.fft_thread)
        self.fft_thread.start()
        self.processAudio.connect(self.fft_worker.process, Qt.QueuedConnection)
        self.fft_worker.resultReady.connect(self._onSpectrumReady)

        # — Timer for update loop —
        self.timer = QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(self.audio_rate)

    def init_audio(self):
        self.count_rate = 20
        self.CHUNK = 1024 * 2
        self.wf_data = np.empty(self.CHUNK, dtype=np.int16)
        self.LOW_C_CUTOFF = self.CHUNK // 128
        self.MED_C_CUTOFF = self.CHUNK // 4
        self.ALL_C_CUTOFF = self.CHUNK // 2 + 1
        self._sp_scale = 2.0 / (128.0 * self.CHUNK)
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=44100,
            input=True,
            output=True,
            frames_per_buffer=self.CHUNK
        )
        # Precompute axes
        self.x = np.arange(0, 2*self.CHUNK, 2)
        self.f_low = np.linspace(0, 44100/128, self.LOW_C_CUTOFF)
        self.f_med = np.linspace(44100/128, 44100/4, self.MED_C_CUTOFF-self.LOW_C_CUTOFF)
        self.f_high = np.linspace(44100/4, 44100/2, self.ALL_C_CUTOFF-self.MED_C_CUTOFF)
        # timer interval
        self.audio_rate = int(self.CHUNK/44100*1000)

    def init_plot(self):
        self.plot_widget = pg.GraphicsLayoutWidget()
        pg.setConfigOptions(antialias=True)
        # waveform
        wf_x = pg.AxisItem(orientation='bottom')
        wf_x.setTicks([[(0,'0'),(1024,'1024'),(2048,'2048'),(3072,'3072'),(4096,'4096')]])
        self.waveform = self.plot_widget.addPlot(title='WAVEFORM',row=1,col=1,axisItems={'bottom':wf_x})
        self.waveform.setYRange(0,255,padding=0)
        self.waveform.setXRange(0,2*self.CHUNK,padding=0.005)
        # spectrum
        sp_x = pg.AxisItem(orientation='bottom')
        sp_x.setTicks([[(np.log10(10),'10Hz'),(np.log10(100),'100Hz'),(np.log10(250),'250Hz'),
                        (np.log10(400),'400Hz'),(np.log10(1000),'1kHz'),(np.log10(22050),'22kHz')]])
        self.spectrum = self.plot_widget.addPlot(title='SPECTRUM',row=2,col=1,axisItems={'bottom':sp_x})
        self.spectrum.setLogMode(x=True,y=True)
        self.spectrum.setYRange(-4,0,padding=0)
        self.spectrum.setXRange(np.log10(20),np.log10(44100/2),padding=0.005)
        for plot in (self.waveform,self.spectrum):
            plot.getViewBox().keyPressEvent=lambda ev:ev.ignore()
        self.traces={}

    def init_ui(self):
        self.setWindowTitle('PyLZR : SSP3CTRUM')
        self.setGeometry(100,100,1200,800)
        layout=QVBoxLayout()
        # avg-rate slider
        self.count_slider=QSlider(Qt.Horizontal,self)
        self.count_slider.setRange(10,50)
        self.count_slider.setValue(self.count_rate)
        self.count_slider.setTickInterval(5)
        self.count_slider.setTickPosition(QSlider.TicksBelow)
        self.count_slider.valueChanged.connect(self._on_count_rate_change)
        self.count_label=QLabel(f'Avgs Calc Rate: {self.count_rate}',self)
        layout.addWidget(self.count_slider)
        layout.addWidget(self.count_label)
        # low-mode sliders
        for mode in range(3):
            lbl=QLabel(self)
            init=[self.LOW_QUIET_MODE_CUTOFF,self.LOW_MODE1_CUTOFF,self.LOW_MODE2_CUTOFF][mode]
            lbl.setText(f"Low {'Quiet' if mode==0 else f'Mode{mode}'} Cutoff: {init}")
            sld=QSlider(Qt.Horizontal,self);
            sld.setRange(0,CUTOFF_SLIDER_MAX);sld.setValue(init)
            sld.valueChanged.connect(lambda v,m=mode,sl=sld:self._on_low_cutoff_change(v,m,sl))
            layout.addWidget(lbl);layout.addWidget(sld)
            setattr(self,f'low_{mode}_label',lbl)
        # high-mode sliders
        for mode in range(3):
            lbl=QLabel(self)
            init=[self.HIGH_QUIET_MODE_CUTOFF,self.HIGH_MODE1_CUTOFF,self.HIGH_MODE2_CUTOFF][mode]
            lbl.setText(f"High {'Quiet' if mode==0 else f'Mode{mode}'} Cutoff: {init}")
            sld=QSlider(Qt.Horizontal,self);
            sld.setRange(0,CUTOFF_SLIDER_MAX);sld.setValue(init)
            sld.valueChanged.connect(lambda v,m=mode,sl=sld:self._on_high_cutoff_change(v,m,sl))
            layout.addWidget(lbl);layout.addWidget(sld)
            setattr(self,f'high_{mode}_label',lbl)
        # key label + plot
        self.key_label=QLabel('Press any key',self)
        layout.addWidget(self.key_label)
        layout.addWidget(self.plot_widget)
        self.setLayout(layout)

    def _on_count_rate_change(self,val):
        self.count_rate=val;self.count_label.setText(f'Avgs Calc Rate: {val}')
        self._low_scale=1000.0/val;self._high_scale=10000.0/val;self.dm_rate=self.DM_TIME_RATE/val
        self._low_means.clear();self._high_means.clear()

    def _on_low_cutoff_change(self,val,mode,slider):
        if mode==0: val=min(val,self.LOW_MODE1_CUTOFF)
        elif mode==1: val=max(val,self.LOW_QUIET_MODE_CUTOFF);val=min(val,self.LOW_MODE2_CUTOFF)
        else: val=max(val,self.LOW_MODE1_CUTOFF)
        if slider.value()!=val:
            with QSignalBlocker(slider): slider.setValue(val)
        setattr(self,['LOW_QUIET_MODE_CUTOFF','LOW_MODE1_CUTOFF','LOW_MODE2_CUTOFF'][mode],val)
        sm.set_cutoff(self.soundmode,val,mode,high=False)
        lbl=getattr(self,f'low_{mode}_label');lbl.setText(f"Low {'Quiet' if mode==0 else f'Mode{mode}'} Cutoff: {val}")

    def _on_high_cutoff_change(self,val,mode,slider):
        if mode==0: val=min(val,self.HIGH_MODE1_CUTOFF)
        elif mode==1: val=max(val,self.HIGH_QUIET_MODE_CUTOFF);val=min(val,self.HIGH_MODE2_CUTOFF)
        else: val=max(val,self.HIGH_MODE1_CUTOFF)
        if slider.value()!=val:
            with QSignalBlocker(slider): slider.setValue(val)
        setattr(self,['HIGH_QUIET_MODE_CUTOFF','HIGH_MODE1_CUTOFF','HIGH_MODE2_CUTOFF'][mode],val)
        sm.set_cutoff(self.soundmode,val,mode,high=True)
        lbl=getattr(self,f'high_{mode}_label');lbl.setText(f"High {'Quiet' if mode==0 else f'Mode{mode}'} Cutoff: {val}")

    def keyPressEvent(self,event:QKeyEvent):
        self.vm.keyboard(event.key())
        self.key_label.setText(f'Key: {event.text()} (code {event.key()})')
        super().keyPressEvent(event)

    def update(self):
        try:
            raw=self.stream.read(self.CHUNK, exception_on_overflow=False)
            audio=np.frombuffer(raw,dtype=np.int16)
            self.wf_data[:]=audio+127
            if 'waveform' not in self.traces:
                self.traces['waveform']=self.waveform.plot(pen='c',width=3)
            self.traces['waveform'].setData(self.x,self.wf_data)
            self.processAudio.emit(self.wf_data.copy())
        except IOError as e: print(f"Audio I/O Error: {e}")

    @pyqtSlot(np.ndarray,np.ndarray,np.ndarray)
    def _onSpectrumReady(self,low,med,high):
        self.sp_data_low,self.sp_data_med,self.sp_data_high=low,med,high
        for name,data,axis in(
            ('spectrum_low',low,self.f_low),('spectrum_med',med,self.f_med),('spectrum_high',high,self.f_high)
        ):
            if name not in self.traces:
                pen={'spectrum_low':'y','spectrum_med':'b','spectrum_high':'m'}[name]
                self.traces[name]=self.spectrum.plot(pen=pen,width=3)
            self.traces[name].setData(axis,data)
        self.run_sm()

    def run_sm(self):
        low_m=self.sp_data_low.mean();high_m=self.sp_data_high.mean()
        self._low_means.append(low_m);self._high_means.append(high_m)
        if len(self._low_means)>=self.count_rate:
            sum_l=sum(self._low_means);sum_h=sum(self._high_means)
            self.low_avg=sum_l*self._low_scale;self.high_avg=sum_h*self._high_scale
            self._low_means.clear();self._high_means.clear()
            self.dm_count=(self.dm_count+1)%int(self.dm_rate)
            if self.vm.sm_ON: self.soundmode.check_mode(self.low_avg,self.high_avg)
            print(f"{txt.YELLOW}{txt.I}LOW: {txt.IOFF}{txt.B}{self.low_avg:.2f}{txt.BOFF}\t"+ 
                  f"{txt.PURPLE}{txt.I}HIGH: {txt.IOFF}{txt.B}{self.high_avg:.2f}{txt.BOFF}")
            print(f"DM COUNT: {self.dm_count}   DM RATE: {self.dm_rate}")
            print(f"DM ON?: {self.soundmode.get_dm_mode_bool()}")
            self.key_label.setText(f"Low Avg: {self.low_avg:.6f} | High Avg: {self.high_avg:.6f}")

    def closeEvent(self,event):
        self.timer.stop();self.stream.stop_stream();self.stream.close();self.p.terminate()
        self.fft_thread.quit();self.fft_thread.wait();super().closeEvent(event)


if __name__=='__main__':
    app=QApplication(sys.argv)
    window=PyLZR()
    window.show()
    sys.exit(app.exec_())
