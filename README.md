
# PyLZR

**Version:** 0.3.0

PyLZR is a Python-based sound-reactive DMX laser light controller, leveraging PyQt5 for the GUI, NumPy and SciPy for FFT audio processing, and MIDI output via `python-rtmidi`. PyLZR reacts in real-time to audio input, converting sound frequencies into MIDI commands to control DMX-compatible laser systems.

**Runs on macOS, Linux and Windows** (Windows needs the free [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html) driver — see [MIDI Output](#midi-output)).

## Features

- **Real-time audio input and FFT analysis** using PyAudio, NumPy, and SciPy.
- **Dynamic GUI** with waveform and spectrum visualization powered by PyQtGraph.
- **Real-time MIDI output** to control DMX devices via virtual or hardware MIDI ports.
- **Customizable spectral threshold sliders** to fine-tune audio responsiveness.
- **Dual-mode functionality** for varied DMX outputs.

## Project Structure

```
pylzr/
├── pyproject.toml           # Build and project metadata
├── requirements.txt         # Project dependencies
├── run.sh                   # Automated setup and launch script
├── src/
│   └── pylzr/
│       ├── __main__.py      # Entry point for console
│       ├── audio/           # PyAudio capture stream
│       ├── analysis/        # FFT worker, windowed averages, sound modes
│       ├── midi/            # MIDI output port + keyboard mapping
│       ├── gui/             # Main window, control/settings/log panels, plots
│       └── core/            # Config constants, logger, terminal text styles
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
   git clone https://github.com/yourusername/pylzr.git
   cd pylzr
   ```

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
   pip install --upgrade pip setuptools wheel
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
- NumPy
- SciPy
- PyAudio
- PyQt5
- pyqtgraph
- python-rtmidi

Refer to [`requirements.txt`](requirements.txt) for exact versions.

## Usage Instructions

- **GUI Sliders:** Adjust spectral frequency cutoff thresholds directly within the GUI.
- **Sound Mode Toggle:** Activate or deactivate MIDI note triggering based on audio analysis via [LSHIFT].
- **Keyboard Controls:** Interact using defined keyboard mappings for MIDI note outputs.

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
