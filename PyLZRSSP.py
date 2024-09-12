import sys
import numpy as np
import pyqtgraph as pg
import pyaudio
import struct
from scipy.fftpack import fft
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QSlider
from PyQt5.QtGui import QKeyEvent
from PyQt5.QtCore import QTimer, Qt
import textClass as txt
import Qtmidi as midi 
import soundModeClass as sm



# PyLZRSSP class
class PyLZRSSP(QWidget): # extend PyQT QWidget class



    ### Initialize PyLZRSSP object #######################################################################
    def __init__(self): # initialize using QWidget superclass constructor
        super().__init__()

        self.LOW_QUIET_MODE_CUTOFF = 0
        self.LOW_MODE1_CUTOFF = 0
        self.LOW_MODE2_CUTOFF = 0

        # Initialize audio and plot variables
        self.init_audio()
        self.init_plot()
        self.init_ui()

        # Audio processing rate for QTimer
        self.audio_rate = 20 # adjust this as needed for audio processing rate

        # Initialize MIDI and set up key press handling
        self.vm = midi.VirtualMIDI()
        
        # Initialize sound mode
        self.init_soundmode()

        # Set up the timer for periodic updates
        self.timer = QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(self.audio_rate)  



    ### Initialize audio spectrum analyzer ###############################################################
    def init_audio(self):

        # Instance fields
        self.count_rate = 20    # spectrum avgs calculating initializations:
        self.low = 0.0
        self.low_avg = 0.0
        self.high = 0.0
        self.high_avg = 0.0
        self.count = 0

        self.wf_data = np.array([]) # audio data arrays initializations:
        self.sp_data = np.array([])
        self.sp_data_low = np.array([])
        self.sp_data_high = np.array([])
        self.sp_data_med = np.array([])

        self.traces = {}    # other audio data array initializations
        self.phase = 0
        self.t = np.arange(0, 3.0, 0.01)

        # Audio setup
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.RATE = 44100
        self.CHUNK = 1024 * 2  # ensure this matches the buffer size

        self.LOW_R_CUTOFF = self.RATE / 128     # spectrum cutoff ranges:
        self.LOW_C_CUTOFF = self.CHUNK // 128

        self.MED_R_CUTOFF = self.RATE / 4
        self.MED_C_CUTOFF = self.CHUNK // 4

        self.HIGH_R_CUTOFF = self.RATE / 4
        self.HIGH_C_CUTOFF = self.CHUNK // 4

        self.ALL_R_CUTOFF = self.RATE / 2
        self.ALL_C_CUTOFF = self.CHUNK // 2

        self.p = pyaudio.PyAudio()  # create audio stream object:
        self.stream = self.p.open(format=self.FORMAT,
                                  channels=self.CHANNELS,
                                  rate=self.RATE,
                                  input=True,
                                  output=True,
                                  frames_per_buffer=self.CHUNK)

        self.x = np.arange(0, 2 * self.CHUNK, 2)    # init visualizer graph axis:
        self.f_low = np.linspace(0, self.LOW_R_CUTOFF, self.LOW_C_CUTOFF)
        self.f_med = np.linspace(self.LOW_R_CUTOFF, self.MED_R_CUTOFF, 
                                 (self.ALL_C_CUTOFF - self.LOW_C_CUTOFF - self.HIGH_C_CUTOFF))
        self.f_high = np.linspace(self.MED_R_CUTOFF, self.ALL_R_CUTOFF, self.HIGH_C_CUTOFF)
        


    ### Initialize SM ####################################################################################
    def init_soundmode(self):

        # SM setup
        self.LOW_QUIET_MODE_CUTOFF = 5000   # low end mode cutoffs: 
        self.LOW_MODE1_CUTOFF = 900
        self.LOW_MODE2_CUTOFF = 1000

        self.HIGH_QUIET_MODE_CUTOFF = 40  # high end mode cutoffs:
        self.HIGH_MODE1_CUTOFF = 100
        self.HIGH_MODE2_CUTOFF = 140

        # Create SM object using SM setup and VM object
        self.soundmode = sm.SoundMode(self.LOW_QUIET_MODE_CUTOFF,   
                                      self.LOW_MODE1_CUTOFF, 
                                      self.LOW_MODE2_CUTOFF, 
                                      self.HIGH_QUIET_MODE_CUTOFF, 
                                      self.HIGH_MODE1_CUTOFF, 
                                      self.HIGH_MODE2_CUTOFF, 
                                      self.vm)



    ### Initialize visualizer ############################################################################
    def init_plot(self):

        # Initialize the plot area
        self.plot_widget = pg.GraphicsLayoutWidget()
        self.plot_widget.resize(1000, 600)
        self.plot_widget.setWindowTitle("PyLZR Audio Spectrum Analyzer")
        
        pg.setConfigOptions(antialias=True)

        # Setup plots
        wf_xlabels = [(0, '0'), (1024, '1024'), (2048, '2048'), (3072, '3072'), (4096, '4096')]
        wf_xaxis = pg.AxisItem(orientation='bottom')
        wf_xaxis.setTicks([wf_xlabels])

        sp_xlabels = [
            (np.log10(10), '10 Hz'),
            (np.log10(100), '100 Hz'),
            (np.log10(250), '250 Hz'),
            (np.log10(400), '400 Hz'),
            (np.log10(1000), '1000 Hz'),
            (np.log10(22050), '22050 Hz')
        ]
        sp_xaxis = pg.AxisItem(orientation='bottom')
        sp_xaxis.setTicks([sp_xlabels])

        self.waveform = self.plot_widget.addPlot(title="WAVEFORM", 
                                                 row=1, col=1, 
                                                 axisItems={'bottom': wf_xaxis})
        self.spectrum = self.plot_widget.addPlot(title="SPECTRUM", 
                                                 row=2, col=1, 
                                                 axisItems={'bottom': sp_xaxis})



    ### Iniitalize PyQT UI ###############################################################################
    def init_ui(self):

        # Initialize the user interface
        self.setWindowTitle('PyLZR : SSP3CTRUM')
        self.setGeometry(100, 100, 1200, 800)

        # Avgs calc rate slider and label
        self.count_slider = QSlider(Qt.Horizontal, self)
        self.count_slider.setMinimum(10)
        self.count_slider.setMaximum(50)
        self.count_slider.setValue(self.count_rate)  # Set initial value
        self.count_slider.setTickInterval(5)
        self.count_slider.setTickPosition(QSlider.TicksBelow)

        self.count_label = QLabel("Avgs Calc Rate: " + str(self.count_rate), self)

        # Update widgets
        self.count_slider.valueChanged.connect(self.update_count_slider_label) # avgs calc rate update
            
        # Key label
        self.key_label = QLabel('Press any key', self)


        layout = QVBoxLayout() # define layout


        # Add widgets to the layout
        layout.addWidget(self.count_slider) # avgs calc rate widget:
        layout.addWidget(self.count_label)

        layout.addWidget(self.key_label)    # plot widgets:
        layout.addWidget(self.plot_widget)

        self.setLayout(layout)  # set layout



    ### Update slider label #############################################################################
    def update_count_slider_label(self):
        # Update the label with the current value of the slider
        value = self.count_slider.value()
        self.count_rate = value
        self.count_label.setText(f'Avgs Calc Rate: {value}')  

    ## idea?
    #def update_slider_label(label, slider):
        #value = slider.value()
        #label.setText(f'Avgs Calc Rate: {value}')
        #return value

    ### Handle key press events ##########################################################################
    def keyPressEvent(self, event: QKeyEvent):

        # Create key event objects
        key = event.key()
        key_name = event.text()  # get the text of the key

        # Send MIDI signal
        self.vm.keyboard(key)

        # Update the key label with the key press information
        self.key_label.setText(f'Key pressed: {key_name} (Qt Key Code: {key})')
        super().keyPressEvent(event)



    ### Plot the data for each graph #####################################################################
    def set_plotdata(self, name, data_x, data_y):

        # Check if plot has already been plotted before (and if so, update data accordingly)
        if name in self.traces: 
            self.traces[name].setData(data_x, data_y)
        # If plot data has not been plotted, set plot and add to plotted data list
        else: 
            match name: # match plot data to respective formatting
                case 'waveform':
                    self.traces[name] = self.waveform.plot(pen='c', width=3)
                    self.waveform.setYRange(0, 255, padding=0)
                    self.waveform.setXRange(0, 2 * self.CHUNK, padding=0.005)
                case 'sepctrum':
                    self.set_sp_plot(name, 'g')
                case 'spectrum_med':
                    self.set_sp_plot(name, 'b')
                case 'spectrum_low':
                    self.set_sp_plot(name, 'y')
                case 'spectrum_high':
                    self.set_sp_plot(name, 'm')
            


    ### Plot the graph data for spectrums ################################################################
    def set_sp_plot(self, name, pen_color):

        # Add plot name to list of plots plotted, set to log mode, set x and y ranges of plots
        self.traces[name] = self.spectrum.plot(pen = pen_color, width = 3)
        self.spectrum.setLogMode(x=True, y=True)
        self.spectrum.setYRange(-4, 0, padding=0)
        self.spectrum.setXRange(np.log10(20), np.log10(self.RATE / 2), padding=0.005)



    ### Update and visualize the data read from the audio stream, and handle SM and MIDI ##################
    def update(self):

        try:
            # Read audio data
            wf_data = self.stream.read(self.CHUNK, exception_on_overflow=False)
            self.wf_data = np.array(struct.unpack(str(self.CHUNK) + 'h', wf_data)) + 127
            self.set_plotdata(name='waveform', data_x=self.x, data_y=self.wf_data)

            # Process spectrum
            self.sp_data = fft(np.array(self.wf_data) - 128)    # convert audio stream data from wavelength to spectrum 

            # section spectrum data into low, med, and high spectrums
            self.sp_data_low = np.abs(self.sp_data[0:int(self.LOW_C_CUTOFF)]) * 2 / (128 * self.CHUNK) 
            self.sp_data_med = np.abs(self.sp_data[int(self.LOW_C_CUTOFF):int(self.MED_C_CUTOFF)]) * 2 / (128 * self.CHUNK)
            self.sp_data_high = np.abs(self.sp_data[int(self.MED_C_CUTOFF):int(self.ALL_C_CUTOFF)]) * 2 / (128 * self.CHUNK)

            # pot the spectrum data
            self.set_plotdata(name='spectrum_med', data_x=self.f_med, data_y=self.sp_data_med)
            self.set_plotdata(name='spectrum_low', data_x=self.f_low, data_y=self.sp_data_low)
            self.set_plotdata(name='spectrum_high', data_x=self.f_high, data_y=self.sp_data_high)

            # label on visualizer
            self.key_label.setText(f'Low Avg: {self.low_avg:.6f} | High Avg: {self.high_avg:.6f}')

            # run SM
            self.run_sm()

        # handle audio stream data read error
        except IOError as e:
            print(f"Error reading audio data: {e}")



    ### Run SM functionalities ###########################################################################
    def run_sm(self):

        # check if it should continue calculating SM avgs
        if self.count < self.count_rate:
            self.low += self.get_sp_avg_low()
            self.high += self.get_sp_avg_high()
            self.count += 1

        # check if should calculate and display SM avgs
        else:
            self.low_avg = (self.low / self.count_rate) * 1000
            self.high_avg = (self.high / self.count_rate) * 10000
            self.low = 0
            self.high = 0
            self.count = 0

            # check if SM on
            if self.vm.sm_ON:
                # check what modes spectrum avgs should be set to 
                self.soundmode.check_mode(self.low_avg, self.high_avg)

            # display spectrum avgs
            print(txt.YELLOW + txt.I + "LOW: " + txt.IOFF + txt.B + str(self.low_avg) + txt.BOFF, end = "\t")
            print(txt.PURPLE + txt.I + "HIGH: " + txt.IOFF + txt.B + str(self.high_avg) + txt.BOFF)
            


    ### Get spectrum avg for low end spectrum data #######################################################
    def get_sp_avg_low(self):
        return np.mean(self.sp_data_low)
    


    ### Get spectrum avg for high end spectrum data ######################################################
    def get_sp_avg_high(self):
        return np.mean(self.sp_data_high)



### >>> Run as main function <<< #########################################################################
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = PyLZRSSP()
    window.show()
    sys.exit(app.exec_())