
# PyLZR

**Version:** 0.4.0

PyLZR is a Python-based sound-reactive DMX laser light controller, leveraging PyQt5 for the GUI, NumPy for FFT audio processing, MIDI output via `python-rtmidi`, and direct DMX output over Art-Net. In addition to manual control, PyLZR reacts in real-time to audio input, converting sound frequencies into commands that control DMX-compatible laser systems through third party lighting software over MIDI or straight to an Art-Net node.

**Runs on macOS, Linux and Windows** (Windows needs the free [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html) driver — see [MIDI Output](#midi-output)).

## Features

- **Real-time audio input and FFT analysis** using PyAudio and NumPy.
- **Dynamic GUI** with waveform and spectrum visualization powered by PyQtGraph.
- **Real-time MIDI output** to control DMX devices via virtual or hardware MIDI ports.
- **Direct DMX output over Art-Net** to a network DMX node (e.g. Pknight CR011R), with a channel tester for exploring a fixture's channels.
- **Customizable spectral threshold sliders** to fine-tune audio responsiveness.
- **Dual-mode functionality** for varied DMX outputs.

## Project Structure

```
pylzr/
├── pyproject.toml           # Build and project metadata, minimum dependency versions
├── requirements.txt         # Exact dependency versions tested in CI
├── run.sh                   # Automated setup and launch script
├── docs/                    # Historical notes (original v0.3 README)
├── tests/                   # pytest suite (fake audio/MIDI/network, runs offscreen)
├── src/
│   └── pylzr/
│       ├── __main__.py      # Entry point for console
│       ├── engine.py        # Audio → FFT → averages → sound mode pipeline (no GUI)
│       ├── audio/           # PyAudio capture stream (callback mode)
│       ├── analysis/        # Frequency bands, FFT worker, windowed averages, sound modes
│       ├── midi/            # MIDI output port + keyboard mapping
│       ├── dmx/             # Art-Net packets, DMX universe, UDP sending, DMX output
│       ├── gui/             # Main window, panels, plots, channel tester, saved settings
│       └── core/            # Config constants, logging, shared interfaces, output switch
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

## DMX Output (Art-Net)

Instead of going through lighting software, PyLZR can send DMX itself to an **Art-Net node**: a small box that receives DMX over Ethernet and outputs it on an XLR cable to your fixtures:

```
PyLZR ──Ethernet (Art-Net)──▶ Art-Net node ──DMX cable──▶ laser
```

Choose where PyLZR's cues go with **Control Mode** in Settings (⚙): **MIDI** (default, as above) or **DMX (Art-Net)**. Only one is active at a time. PyLZR sends DMX only while DMX is chosen; switching back to MIDI (or closing PyLZR) sends one blackout frame first, so the fixtures go dark rather than freezing on their last look.

> In this version DMX mode sends what the **channel tester** sets (below). Sound Mode and keyboard cues don't drive DMX yet — scenes for that come in a later version. Use MIDI mode for shows in the meantime.

### 1. Set up the node (Pknight CR011R)

On the node's own menu (see its manual):
- **Transmit mode:** Art-Net → DMX (the node is bidirectional; this is the direction you need).
- **IP address:** factory default `10.201.6.100`, subnet mask `255.0.0.0`. Leave it, or change it — PyLZR just needs to know it.
- **Net / SubNet / Universe:** factory default `0 / 0 / 0`. PyLZR's **Net / Sub / Uni** boxes must match.

### 2. Connect the computer

Use a **direct Ethernet cable** from the computer to the node (Wi-Fi is less reliable and adds timing jitter). The computer's Ethernet port then needs a fixed address on the node's network. With the node's default address, use `10.201.6.50` / `255.0.0.0` (any `10.x.x.x` address the node isn't using works):

- **Windows 11:** Settings → Network & internet → Ethernet → *IP assignment* → **Edit** → **Manual** → turn on **IPv4** → IP address `10.201.6.50`, Subnet mask `255.0.0.0`, leave Gateway and DNS empty → **Save**.
- **macOS:** System Settings → Network → your Ethernet / USB Ethernet adapter → **Details…** → **TCP/IP** → Configure IPv4: **Manually** → IP Address `10.201.6.50`, Subnet Mask `255.0.0.0`, leave Router empty → **OK**.

Wi-Fi stays connected for internet; only the Ethernet port changes. (Undo it later by setting the Ethernet port back to automatic/DHCP.)

### 3. Point PyLZR at the node

In Settings (⚙) → **DMX (ART-NET)**: enter the node's **Node IP** and its **Net / Sub / Uni**, then set **Control Mode** to **DMX (Art-Net)**. These are saved with your other settings.

The **DMX** indicator at the top of Settings shows what's happening:

| Indicator | Meaning |
|---|---|
| ⚫ grey — `Off` | Not sending (Control Mode is MIDI). |
| 🟢 green — `via 10.201.6.50` | Sending. Packets leave from the computer address shown, on the node's network. |
| 🟡 amber — `via 192.168.… — check cable / IP` | Packets are leaving from a *different* network (usually Wi-Fi), so they're going to your router, not the node. Check the Ethernet cable is plugged in and step 2 is done. Rechecked every second. |
| 🔴 red — e.g. `network unreachable` | The computer couldn't send at all — no network route to that address. |

Art-Net has no delivery receipt, so green means *sent towards the node*, not *received by it*. If green but nothing happens, check the node's data light/screen, its Net/SubNet/Universe and transmit mode, and the DMX cable to the fixture.

### Channel tester

With Control Mode on DMX, **Channel tester…** opens a window with a slider (and a box to type an exact value, 0–255) for each DMX channel. Choose the **start channel** and how many **channels** to show (up to 32). Values go out **live**: use it to find out what each of your fixture's channels does, e.g. which value ranges select which colour or pattern.

- Changing the start channel puts every slider back to 0, so values never jump onto channels you haven't looked at. **All 0** zeroes the shown channels.
- Closing the window (or leaving DMX mode) releases the channels; it reopens at 0.

> ⚠️ **Laser safety:** a laser responds the moment a slider moves. Aim it safely (never at people or reflective surfaces) and keep it covered or off while you explore.

### Troubleshooting

- **Amber indicator:** see the table above; almost always the cable or the computer's IP address.
- **See the packets:** [Wireshark](https://www.wireshark.org/) with the display filter `udp.port == 6454` shows every Art-Net packet PyLZR sends (about 40 per second, "ArtDmx").
- **Firewall:** PyLZR only *sends* Art-Net, which firewalls don't block by default.

## Dependencies

PyLZR requires:
- Python 3.11 or 3.12 (newer versions have no prebuilt `python-rtmidi` package and need a C++ compiler to install)
- PortAudio (macOS/Linux only - see [Manual Setup](#manual-setup))
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
- **Saved Settings:** Cutoffs, averaging rate, gain, input device, MIDI port, FFT window, smoothing, log level, Control Mode and the DMX node (IP, Net/SubNet/Universe) are remembered between launches. Use **Reset to defaults** in Settings (⚙) to start over. They're stored in `PyLZR/PyLZR.ini` in your user config folder (`%APPDATA%` on Windows, `~/.config` on macOS/Linux).
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

The tests replace audio, MIDI and the network with in-memory fakes and run Qt offscreen, so they need no microphone, MIDI port, Art-Net node or display, and they behave the same on every OS. (They never send Art-Net onto your network; the few real-socket tests use 127.0.0.1 only.) GitHub Actions runs them on Windows, macOS and Linux for every push.

`tests/test_pipeline_golden.py` feeds fixed synthetic audio through the whole app and compares every FFT frame, average and MIDI note with `tests/golden/pipeline.json`. If a change is *meant* to alter that output, regenerate the file with `PYLZR_UPDATE_GOLDEN=1 pytest tests/test_pipeline_golden.py` and review its diff.

## Creator's Commentary

This project grew from a hobby. I needed an inexpensive, entry-level budget tool to expand what I could do with a DMX laser that I couldn't find much support for in other software. My hopes are that PyLZR helps others who would like to get into laser lighting as a solid base to jump off of or offers some inspiration for others' projects. 

PyLZR is a continuous work in progress. Recent version have:
- added Windows support (via loopMIDI) alongside macOS and Linux, with the automated tests running on all three for every change
- restructured the code into a GUI-free audio engine with separate audio, analysis, MIDI and DMX packages, so it's easier to extend and reuse
- added saved settings, a spectrum plotted at true frequencies, and audio capture that no longer drops sound when the window is busy
- taken the first step towards standalone DMX: PyLZR can now send DMX straight to an Art-Net node, with a channel tester for exploring a fixture's channels.

For shows, I still recommend MIDI mode for now: map PyLZR's MIDI notes to scenes in software that works as a MIDI-controlled lighting desk (such as SoundSwitch and its "static looks").

DMX mode can't play scenes yet. That is what I'm working on next in development (roughly in this order):
- **Fixture profiles**: describe a fixture's channels (using the Open Fixture Library (OFL) format) so PyLZR knows what every value does. Shows and settings are written in terms of things like colour, size and speed rather than channel numbers, so fixtures can be swapped without redoing everything
- **Scenes**: Sound Mode and keyboard cues driving DMX directly, with no other lighting software needed
- **A more dynamic sound-reactive mode**: small changes in the music smoothly nudge things like speed, size or position, while big changes switch scenes
- **Timecoded shows**: program looks against an audio file (or import them from a DAW) and play them back
- **Machine learning**: training PyLZR on those shows so its live, sound-reactive output reacts the way I would program it by hand

A C++ version is also in early development, in hopes that something as time-sensitive as live-audio analysis response latenecy will be reduced as much as possible and expand use cases for this software to include individuals who may otherwise found themselves somewhat restricted by non-high-end machines.

Multiple expanded functionalities including a more dynamically sound-reactive mode via OLA, custom user-created fixture profiles support, etc are currently in development. In addition, a C++ version is also in early development. I am currently working on finalizing support for Windows as well. 

Keep in mind, I've personally only tested this application on macOS 12.7.6 and Windows 11. The automated tests run on macOS, Windows, and Linux, but they use simulated audio, MIDI, and network devices so real hardware may still turn up issues. Please open an issue if you run into one. Contributions are welcome! If you have ideas or questions, feel free to message me on any platform as I would be more than happy to answer, talk, discuss, brainstorm, or whatever. I'll never complain about having more minds, perspectives, and ideas on this, and I'm always open to learning more from others.

Again, this project grew from a hobby. I found a need for an inexpensive tool to expand the functionality for a DMX laser light machine that I couldn't find much support for in other software applications, and as a broke college student at the time I was working within an extremely tight budget. If you find yourself in a similar situation, I hope this project helps you or gives you some inspiration for your own projects! 

## License

PyLZR is licensed under the MIT License. See the [LICENSE](LICENSE) file for more details.
