
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
├── pyproject.toml           # Project metadata, minimum dependency versions, uv settings
├── uv.lock                  # Exact dependency versions tested in CI (all OSes)
├── requirements.txt         # The same versions exported from uv.lock, for pip
├── .python-version          # Python version uv uses (3.12)
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

## Installation

PyLZR is run with **[uv](https://docs.astral.sh/uv/)**, a tool that sets up the right Python version and all of PyLZR's packages in a private folder (`.venv`) and starts the app. The same command works on Windows, macOS and Linux. (Prefer plain `pip`? See [Without uv](#without-uv-pip).)

### 1. Install the prerequisites

- **Windows** (PowerShell or Command Prompt):
  ```powershell
  winget install --id=astral-sh.uv -e
  py install 3.12
  ```
  Then open a **new** terminal so `uv` is found. No winget? Use `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"` for uv, and the Python 3.12 installer from [python.org](https://www.python.org/downloads/windows/) for Python. Python 3.12 is installed up front because many PCs (Smart App Control, school or work policies) block the Python builds uv would otherwise download; uv then uses the python.org one instead. For MIDI mode you'll also want [loopMIDI](#midi-output).
- **macOS** ([Homebrew](https://brew.sh) required):
  ```bash
  xcode-select --install          # C compiler, if not installed yet
  brew install portaudio uv
  ```
- **Linux** (Debian/Ubuntu; use your distribution's equivalents elsewhere):
  ```bash
  sudo apt install portaudio19-dev build-essential
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

On macOS and Linux, PyAudio (audio input) is compiled on first install, which is why PortAudio and a C compiler are needed. On Windows it comes ready-made.

### 2. Get PyLZR

```bash
git clone https://github.com/oh-ok-i-get-it/PyLZR.git
cd PyLZR
```

No Git? Use **Code → Download ZIP** on the GitHub page, unzip it, and open a terminal in that folder.

### 3. Run it

```bash
uv run pylzr
```

The first run takes a minute: uv picks Python 3.12 (see `.python-version`), creates `.venv`, and installs the exact package versions tested in CI (`uv.lock`). Later runs start straight away.

- **Updating:** `git pull`, then `uv run pylzr`. uv installs any changed packages automatically.
- **Starting fresh:** delete the `.venv` folder and run `uv run pylzr` again.

### First launch

- **macOS** asks whether your terminal may use the microphone. Allow it (or later: System Settings → Privacy & Security → Microphone).
- **Windows:** if the level meter in Settings (⚙) stays empty, turn on Settings → Privacy & security → Microphone → *Let desktop apps access your microphone*.
- Pick your input in Settings (⚙) → **Device**. PyLZR remembers it.

### Without uv (pip)

<details>
<summary>Install with Python's own <code>venv</code> and <code>pip</code> instead</summary>

You need **Python 3.11 or 3.12** (3.13 and newer can't install PyLZR's MIDI library). Install the prerequisites from step 1 except uv. On Debian/Ubuntu also install `python3.12-venv`. These commands use the environment's Python directly, so there's nothing to activate.

**Windows** (PowerShell or Command Prompt):
```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt -e .
.venv\Scripts\python -m pylzr
```

**macOS / Linux:**
```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -e .
.venv/bin/python -m pylzr
```
On Apple Silicon Macs, if the install fails with `portaudio.h` not found, point the build at Homebrew and run the install line again:
```bash
CFLAGS="-I$(brew --prefix)/include" LDFLAGS="-L$(brew --prefix)/lib" .venv/bin/python -m pip install -r requirements.txt -e .
```

`requirements.txt` holds the same tested versions as `uv.lock`. To update later: `git pull`, then rerun the install line.
</details>

### Troubleshooting installation

| Message | Fix |
|---|---|
| `requires a different Python: 3.13…` (or newer) | PyLZR needs Python 3.11 or 3.12. With uv this is automatic; with pip, create `.venv` with 3.12 as shown above. |
| `An Application Control policy has blocked this file` (Windows) | Your PC blocks uv's downloaded Python. Install Python 3.12 from python.org (or `py install 3.12`), run `uv python uninstall 3.12`, then `uv run pylzr` again. |
| `invalid peer certificate: UnknownIssuer` | Your network (school/work) inspects HTTPS. Run `uv run --system-certs pylzr`, or set the environment variable `UV_SYSTEM_CERTS=1`. |
| `portaudio.h` file not found | Install PortAudio and a C compiler (step 1), then run again. |
| Linux: `Could not load the Qt platform plugin "xcb"` | `sudo apt install libxcb-xinerama0 libxkbcommon-x11-0` |

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
- Python 3.11 or 3.12 (`python-rtmidi` has no prebuilt packages for newer versions). uv uses 3.12 automatically.
- PortAudio and a C compiler (macOS/Linux only; see [Installation](#1-install-the-prerequisites))
- NumPy
- PyAudio
- PyQt5
- pyqtgraph
- python-rtmidi

[`pyproject.toml`](pyproject.toml) lists the minimum versions; [`uv.lock`](uv.lock) pins the exact versions tested in CI, and [`requirements.txt`](requirements.txt) is exported from it for pip.

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
uv run --extra dev pytest
```

(With pip: `.venv/bin/python -m pip install -e ".[dev]"` once, then `.venv/bin/python -m pytest`; on Windows use `.venv\Scripts\python`.) Lint with `uv run --extra dev ruff check .`.

The tests replace audio, MIDI and the network with in-memory fakes and run Qt offscreen, so they need no microphone, MIDI port, Art-Net node or display, and they behave the same on every OS. (They never send Art-Net onto your network; the few real-socket tests use 127.0.0.1 only.) GitHub Actions runs them on Windows, macOS and Linux for every push.

`tests/test_pipeline_golden.py` feeds fixed synthetic audio through the whole app and compares every FFT frame, average and MIDI note with `tests/golden/pipeline.json`. If a change is *meant* to alter that output, regenerate the file with `PYLZR_UPDATE_GOLDEN=1 uv run --extra dev pytest tests/test_pipeline_golden.py` (PowerShell: `$env:PYLZR_UPDATE_GOLDEN=1; uv run --extra dev pytest tests/test_pipeline_golden.py`) and review its diff.

### Changing Dependencies

Edit the `dependencies` in [`pyproject.toml`](pyproject.toml), then update the lock and its pip export, and commit all three files:

```bash
uv lock
uv export --frozen --no-hashes --no-emit-project -o requirements.txt
```

CI fails if `uv.lock` or `requirements.txt` are out of date. To move every package to its newest allowed version, use `uv lock --upgrade` instead of `uv lock`.

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
