
# PyLZR

**Version:** 0.4.0

PyLZR is a Python-based sound-reactive DMX laser light controller, leveraging PyQt5 for the GUI, NumPy for FFT audio processing, and MIDI output via `python-rtmidi`. PyLZR reacts in real-time to audio input, converting sound frequencies into MIDI commands to control DMX-compatible laser systems.

**Runs on macOS, Linux and Windows** (Windows needs the free [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html) driver — see [MIDI Output](#midi-output)).

## Features

- **Real-time audio input and FFT analysis** using PyAudio and NumPy.
- **Dynamic GUI** with waveform and spectrum visualization powered by PyQtGraph.
- **Real-time MIDI output** to control DMX devices via virtual or hardware MIDI ports.
- **Customizable spectral threshold sliders** to fine-tune audio responsiveness.
- **Dual-mode functionality** for varied DMX outputs.

## Project Structure

```
pylzr/
├── pyproject.toml           # Build and project metadata, minimum dependency versions
├── requirements.txt         # Exact dependency versions tested in CI
├── run.sh                   # Automated setup and launch script
├── docs/                    # Historical notes (original v0.3 README)
├── tests/                   # pytest suite (fake audio/MIDI, runs offscreen)
├── src/
│   └── pylzr/
│       ├── __main__.py      # Entry point for console
│       ├── engine.py        # Audio → FFT → averages → sound mode pipeline (no GUI)
│       ├── audio/           # PyAudio capture stream (callback mode)
│       ├── analysis/        # Frequency bands, FFT worker, windowed averages, sound modes
│       ├── midi/            # MIDI output port + keyboard mapping
│       ├── gui/             # Main window, panels, plots, saved settings
│       └── core/            # Config constants, logging, shared interfaces
└── README.md
```

## Installation and Usage

### Automated Setup (Recommended)

A bash script simplifies setup and launch (on Windows, run it from Git Bash):

```bash
./run.sh
```

This script will:
- Create and activate a virtual environment (`.venv`)
- Upgrade `pip`, `setuptools`, and `wheel`
- Install required dependencies
- Install PyLZR in editable mode
- Launch the application

### Manual Setup

1. **Clone Repository:**
   ```bash
   git clone https://github.com/oh-ok-i-get-it/PyLZR.git
   cd PyLZR
   ```

   **macOS only:** PyAudio is built from source on macOS and needs PortAudio first:
   ```bash
   brew install portaudio
   ```
   (On Linux, install your distribution's PortAudio development package, e.g. `sudo apt install portaudio19-dev`.)

2. **Set up Python Virtual Environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
   On Windows (PowerShell):
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

3. **Install Dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Install PyLZR:**
   ```bash
   pip install -e .
   ```

### Launch PyLZR

- **Via Module:**
  ```bash
  python -m pylzr
  ```

- **Via Console Command:**
  ```bash
  pylzr
  ```

## MIDI Output

PyLZR sends its MIDI notes to a port named **`PyLZR-MIDI`**, which lighting software (e.g. SoundSwitch) listens to.

- **macOS / Linux:** PyLZR creates the `PyLZR-MIDI` virtual port itself. Nothing to set up.
- **Windows:** Windows can't create virtual MIDI ports, so a loopback driver provides it:
  1. Install [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html).
  2. In loopMIDI, type `PyLZR-MIDI` as the new port name and click **+**.
  3. Keep loopMIDI running, then start PyLZR. It finds the port automatically (it appears as `PyLZR-MIDI 1`).

  If loopMIDI wasn't running when PyLZR started, the MIDI indicator in Settings (⚙) shows red. Create the port, then open Settings again and PyLZR connects.

On any OS, the **MIDI Out** dropdown in Settings lets you send to a different port instead, such as a hardware MIDI interface or a macOS IAC bus.

## Dependencies

PyLZR requires:
- Python 3.11 or 3.12 (newer versions have no prebuilt `python-rtmidi` package and need a C++ compiler to install)
- PortAudio (macOS/Linux only — see [Manual Setup](#manual-setup))
- NumPy
- PyAudio
- PyQt5
- pyqtgraph
- python-rtmidi

[`pyproject.toml`](pyproject.toml) lists the minimum versions; [`requirements.txt`](requirements.txt) pins the exact versions tested in CI.

## Usage Instructions

- **GUI Sliders:** Adjust spectral frequency cutoff thresholds directly within the GUI.
- **Sound Mode Toggle:** Activate or deactivate MIDI note triggering based on audio analysis via [SHIFT]. Turning it on sends the cue for the current audio straight away. Sound Mode always starts off.
- **Keyboard Controls:** Interact using defined keyboard mappings for MIDI note outputs. Holding a key sends its note once.
- **Saved Settings:** Cutoffs, averaging rate, gain, input device, MIDI port, FFT window, smoothing and log level are remembered between launches. Use **Reset to defaults** in Settings (⚙) to start over. They're stored in `PyLZR/PyLZR.ini` in your user config folder (`%APPDATA%` on Windows, `~/.config` on macOS/Linux).
- **New audio inputs:** Plugged in a microphone or interface after starting PyLZR? Click **↻** next to the input device in Settings to rescan. Audio pauses for a moment.
- **Spectrum:** Plotted against true frequencies. Yellow = low band (0–172 Hz, drives LOW), blue = mid, magenta = high band (5.5–11 kHz, drives HIGH), grey = 11–22 kHz (shown only).
- **Performance → Overflow:** Counts audio chunks lost because the computer couldn't keep up. It should stay at 0.

## Development and Contribution

1. Fork the project repository.
2. Create your feature branch (`git checkout -b feature/your-feature`).
3. Commit changes (`git commit -am 'Add some feature'`).
4. Push to your branch (`git push origin feature/your-feature`).
5. Open a Pull Request.

Ensure adherence to the existing coding style and provide meaningful commit messages.

### Running Tests

```bash
pip install -e ".[dev]"
pytest
```

The tests replace audio and MIDI with in-memory fakes and run Qt offscreen, so they need no microphone, MIDI port or display, and they behave the same on every OS. GitHub Actions runs them on Windows, macOS and Linux for every push.

`tests/test_pipeline_golden.py` feeds fixed synthetic audio through the whole app and compares every FFT frame, average and MIDI note with `tests/golden/pipeline.json`. If a change is *meant* to alter that output, regenerate the file with `PYLZR_UPDATE_GOLDEN=1 pytest tests/test_pipeline_golden.py` and review its diff.

## Creator's Commentary

Please note that this is a continuous work in progress. Multiple expanded functionalities including a more dynamically sound-reactive mode via OLA, custom user-created fixture profiles support, etc are currently in development. In addition, a C++ version is also in early development. I am currently working on finalizing support for Windows as well. 
Additionally, bear in mind that I have only tested this version (0.4.0) on MacOS 12.7.6 so although I believe it should work on Linux systems and later MacOS versions, I cannot guarantee it.
With the current version only supporting MIDI control, I recommend using some other software that essentially works as a MIDI controller for various "scenes" or modes (such as SoundSwitch with their "static looks"), and mapping PyLZR's MIDI outputs with their respective modes.
Finally, there is further restructuring of the code that I would like to do to make this project more modularized and reusable, so please be patient or feel free to contribute!

This project grew from a hobby. I found a need for an inexpensive tool to expand the functionality for a DMX laser light machine that I couldn't find much support for in other software applications. If you find yourself in a similar situation, I hope this project helps you or gives you some inspiration for your own projects! 

## License

PyLZR is licensed under the MIT License. See the [LICENSE](LICENSE) file for more details.
