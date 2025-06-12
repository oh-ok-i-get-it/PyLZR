
__version__ = "0.3.0"


from .Qtmidi import VirtualMIDI
from .soundModeClass import SoundMode, set_cutoff
from .fftWorker import FFTWorker
from . import textClass


__all__ = [
    "PyLZR",
    "VirtualMIDI",
    "SoundMode",
    "FFTWorker",
    "textClass"
]




