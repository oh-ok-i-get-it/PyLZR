"""
Main file for PyLZR-

probably first going to start with building a audio spectrum analyzer 
to read microphone input, then send MIDI signal to virtual MIDI device
which will be connected to SoundSwitch until I can build or find a 
good DMX protocol API

AudioVisualizer -> virtual MIDI device/keyboard -> SoundSwitch -> DMX adapter -> laser


Note to self: decide to either bring over old PyLZR code from PyCharm or 
start from scratch on GUI (possibly better to restart because might not 
use OpenDMX or OLA - but maybe try OLA with ArtNet adapter?)

"""
import pyaudio




