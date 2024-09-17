PyLZR

v0.2

!!!
A future version of PyLZR with runtime adjustable sound mode CUTOFFs, standalone DMX functionality 
(including custom fixture profiles), dynamic sound mode, and improved optimization and codebase is 
currently in development. However, it is not publicly available yet.
!!!

DESCRIPTION:
Python program for basic DMX controlled laser machines to expand functionalities to include:

    * keyboard control: 
        Quickly turn on/off sound mode and easily switch the active mapped laser mode by pressing the 
        appropriate keyboard key. Allows for live manual control of laser modes.

    * customizable live audio sound reactivity:
        Live audio is read from the system mic. The audio wavelength and spectrum are displayed for the 
        user in a visualizer. The high and low ends of the spectrum are analyzed to compute the overall 
        average intensity of each over given time intervals. The results determine the appropriate sound 
        mode as defined by the CUTOFF values set in the source code. Changes in these sound modes send 
        updates which control the mapped laser modes. These averages and updates are displayed to the 
        console for the user.


TO USE:
Run the PyLZR.py file in the terminal console.
The [LSHIFT] key is used as to toggle sound mode on/off (off by default). 
The slider at the top of the visualizer window can be moved to adjust the rate of the intervals at which 
the live audio is analyzed (lower value for faster/shorter, higher for slower/larger).
To adjust the CUTOFF values for the sound modes, change the integer values assigned to their respective 
variables in lines 26-32 of the source code for the PyLZR.py file. Keep in mind the program needs to be 
recompiled/restarted after adjusting these values for the adjustment to take effect. 


MODULES/LIBRARIES USED:
    * PyAudio
    * NumPy
    * PyQt5
    * PyQtGraph
    * SciPy
    * python-rtmidi


VERSION NOTE:
There are a few aspects from this version that are not ideal but were done in the interest of time (it 
was a higher priority to have functional software for my first venue gig than to implement certain 
aspects and features):

    * the use of the SoundSwitch software to handle DMX protocol. 
        As a result, a virtual MIDI controller is created and used to communicate with SoundSwitch by 
        allowing the user to map keyboard keys (corresponding to the virtual MIDI) to various customizable 
        modes in SoundSwitch. 

    * sound mode CUTOFF values being non-adjustable during runtime and requiring editing of source code 

Keep in mind:

    * because of the priority of functionality over non-essential features due to time constraints, this 
    version is not fully optimized nor is the source code designed in a way that is preferable. 

    * this version is mainly being kept as a record of the first functional version of PyLZR because it 
    was successful for my first live venue gig

    * this version was only tested on MacOS 12.7.5 and later and has not been tested on Windows or Linux

