#!/usr/bin/env bash
# Install, update or uninstall PyLZR on macOS and Linux.
#
#   1. Installs what's missing (Xcode tools + Homebrew + PortAudio + uv on
#      macOS; PortAudio, a C compiler and uv on Linux), after asking once.
#   2. Downloads PyLZR into the per-user app folder (or updates it), unless run
#      from inside a PyLZR folder or given --source.
#   3. Sets it up with `uv sync --locked` (the exact versions tested in CI).
#   4. Adds an app (Applications / app menu), a Desktop shortcut and a `pylzr`
#      command.
# Run it again to update. Saved settings are never touched.
#
#   From the web:  curl -LsSf https://raw.githubusercontent.com/oh-ok-i-get-it/PyLZR/main/install.sh | bash
#   From a clone:  bash install.sh
#
# Written for bash 3.2, the version macOS ships.

set -euo pipefail

REPO_URL='https://github.com/oh-ok-i-get-it/PyLZR'

usage() {
    cat <<'EOF'
Usage: install.sh [options]

  -y, --yes           Don't ask before installing prerequisites
      --source DIR    Use this PyLZR folder instead of downloading one
      --no-launchers  Skip the app, Desktop shortcut and `pylzr` command
      --uninstall     Remove the launchers and the downloaded copy
                      (keeps settings, uv, Python and system packages)
  -h, --help          Show this help

From the web, pass options after `bash -s --`, e.g.:
  curl -LsSf https://raw.githubusercontent.com/oh-ok-i-get-it/PyLZR/main/install.sh | bash -s -- --yes
EOF
}

YES=false
SOURCE=''
LAUNCHERS=true
UNINSTALL=false
while [ $# -gt 0 ]; do
    case "$1" in
        -y|--yes)       YES=true ;;
        --source)       [ $# -ge 2 ] || { usage; exit 2; }; SOURCE="$2"; shift ;;
        --no-launchers) LAUNCHERS=false ;;
        --uninstall)    UNINSTALL=true ;;
        -h|--help)      usage; exit 0 ;;
        *)              echo "Unknown option: $1"; usage; exit 2 ;;
    esac
    shift
done

OS="$(uname -s)"
case "$OS" in
    Darwin)
        APP_DIR="$HOME/Library/Application Support/PyLZR"
        MAC_APP="$HOME/Applications/PyLZR.app"
        DESKTOP_LINK="$HOME/Desktop/PyLZR.app" ;;
    Linux)
        DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
        APP_DIR="$DATA_HOME/pylzr"
        DESKTOP_FILE="$DATA_HOME/applications/pylzr.desktop"
        DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
        DESKTOP_LINK="$DESKTOP_DIR/pylzr.desktop" ;;
    *)
        echo "This installer is for macOS and Linux; on Windows use install.ps1."; exit 1 ;;
esac
CODE_DIR="$APP_DIR/app"                 # downloaded copy of PyLZR
BIN_LINK="$HOME/.local/bin/pylzr"
SETTINGS_FILE="$HOME/.config/PyLZR/PyLZR.ini"

if [ -t 1 ]; then BOLD=$'\033[1m'; CYAN=$'\033[36m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RESET=$'\033[0m'
else BOLD=''; CYAN=''; GREEN=''; YELLOW=''; RESET=''; fi

say()  { printf '%s\n' "$*"; }
step() { printf '\n%s==> %s%s\n' "$CYAN$BOLD" "$*" "$RESET"; }
ok()   { printf '%s%s%s\n' "$GREEN" "$*" "$RESET"; }
warn() { printf '%s%s%s\n' "$YELLOW" "$*" "$RESET"; }
die()  { printf '%sError: %s%s\n' "$YELLOW" "$*" "$RESET" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

confirm() {
    $YES && return 0
    # Read from the terminal: with `curl ... | bash`, stdin is the script itself
    local answer=''
    if [ -r /dev/tty ]; then
        printf '%s [Y/n] ' "$1" > /dev/tty
        read -r answer < /dev/tty || answer='n'
    else
        answer='n'                      # nobody to ask
    fi
    case "$answer" in ''|[Yy]*) return 0 ;; *) return 1 ;; esac
}

# Root (e.g. in a container) has no sudo, and doesn't need it
if [ "$(id -u)" -eq 0 ]; then SUDO=''; else SUDO='sudo'; fi

# Tools installed by Homebrew or uv's installer may not be on this shell's PATH yet
add_known_paths() {
    local dir
    for dir in "$HOME/.local/bin" /opt/homebrew/bin /usr/local/bin; do
        case ":$PATH:" in *":$dir:"*) ;; *) [ -d "$dir" ] && PATH="$dir:$PATH" ;; esac
    done
    export PATH
}

# --- Which PyLZR folder -----------------------------------------------------

is_pylzr_folder() {
    [ -f "$1/pyproject.toml" ] && grep -q '^name = "pylzr"' "$1/pyproject.toml"
}

TARGET=''
MANAGED=false
resolve_folder() {
    if [ -n "$SOURCE" ]; then
        TARGET="$(cd "$SOURCE" && pwd)" || die "$SOURCE doesn't exist."
        is_pylzr_folder "$TARGET" || die "$TARGET is not a PyLZR folder (no pyproject.toml for pylzr)."
        return
    fi
    # Run as a file from a clone (not piped from the web)
    local script="${BASH_SOURCE[0]:-}"
    if [ -n "$script" ] && [ -f "$script" ]; then
        local here
        here="$(cd "$(dirname "$script")" && pwd)"
        if is_pylzr_folder "$here"; then TARGET="$here"; return; fi
    fi
    TARGET="$CODE_DIR"
    MANAGED=true
}

# --- Prerequisites ----------------------------------------------------------

has_portaudio_linux() {
    if have pkg-config && pkg-config --exists portaudio-2.0; then return 0; fi
    [ -f /usr/include/portaudio.h ] || [ -f /usr/local/include/portaudio.h ]
}

install_prerequisites() {
    step 'Checking prerequisites'
    add_known_paths
    local missing=''

    if [ "$OS" = Darwin ]; then
        xcode-select -p >/dev/null 2>&1 || missing="$missing
  - Xcode Command Line Tools (C compiler)"
        have brew                       || missing="$missing
  - Homebrew (installs PortAudio and uv)"
        { have brew && brew list --formula portaudio >/dev/null 2>&1; } || missing="$missing
  - PortAudio (audio input)"
        have uv                         || missing="$missing
  - uv (sets up and runs PyLZR)"
    else
        has_portaudio_linux             || missing="$missing
  - PortAudio development files (audio input)"
        { have cc || have gcc; }        || missing="$missing
  - a C compiler"
        have curl                       || missing="$missing
  - curl"
        have uv                         || missing="$missing
  - uv (sets up and runs PyLZR)"
    fi

    if [ -z "$missing" ]; then ok 'All prerequisites are installed.'; return; fi
    say "Missing:$missing"
    confirm 'Install them now?' || die 'Prerequisites not installed; nothing changed.'

    if [ "$OS" = Darwin ]; then install_prerequisites_mac; else install_prerequisites_linux; fi
    add_known_paths
    have uv || die 'uv was installed but is not on PATH yet. Open a new terminal and run this again.'
    ok 'Prerequisites installed.'
}

install_prerequisites_mac() {
    if ! xcode-select -p >/dev/null 2>&1; then
        xcode-select --install || true
        die "Finish installing the Command Line Tools in the window that opened, then run this installer again."
    fi
    if ! have brew; then
        # Homebrew's official installer (asks for your password)
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        add_known_paths
        have brew || die 'Homebrew was installed but is not on PATH yet. Open a new terminal and run this again.'
    fi
    brew list --formula portaudio >/dev/null 2>&1 || brew install portaudio
    have uv || brew install uv
}

install_prerequisites_linux() {
    if have apt-get; then
        # The libxcb/libxkbcommon packages let Qt open its window on minimal systems
        $SUDO apt-get update
        $SUDO apt-get install -y portaudio19-dev build-essential curl libxcb-xinerama0 libxkbcommon-x11-0
    elif have dnf; then
        $SUDO dnf install -y portaudio-devel gcc curl
    elif ! has_portaudio_linux || ! { have cc || have gcc; } || ! have curl; then
        die 'Install PortAudio (development files), a C compiler and curl with your package manager, then run this again.'
    fi
    have uv || curl -LsSf https://astral.sh/uv/install.sh | sh      # installs into ~/.local/bin
}

# --- Code -------------------------------------------------------------------

update_code() {
    local dir="$1"
    step "Getting PyLZR into $dir"
    mkdir -p "$APP_DIR"
    if have git; then
        if [ -d "$dir/.git" ]; then
            git -C "$dir" pull --ff-only
        else
            rm -rf "$dir"
            git clone "$REPO_URL" "$dir"
        fi
        return
    fi
    # No git: download the latest main and replace the code, keeping .venv
    local tmp
    tmp="$(mktemp -d)"
    curl -LsSf "$REPO_URL/archive/refs/heads/main.tar.gz" | tar -xz -C "$tmp"
    mkdir -p "$dir"
    find "$dir" -mindepth 1 -maxdepth 1 ! -name .venv -exec rm -rf {} +
    (cd "$tmp/PyLZR-main" && find . -mindepth 1 -maxdepth 1 -exec mv {} "$dir/" \;)
    rm -rf "$tmp"
}

sync_environment() {
    step 'Installing PyLZR and its packages (uv sync --locked)'
    export UV_SYSTEM_CERTS=1            # works behind HTTPS-inspecting networks too
    if $MANAGED; then
        uv sync --locked --project "$1"
    else
        uv sync --locked --inexact --project "$1"     # your folder: keep extra packages (e.g. dev tools)
    fi
}

# --- Launchers --------------------------------------------------------------

install_command() {
    mkdir -p "$(dirname "$BIN_LINK")"
    ln -sfn "$1/.venv/bin/pylzr" "$BIN_LINK"
    say "  $BIN_LINK"
    case ":$PATH:" in
        *":$HOME/.local/bin:"*) ;;
        *) warn "  ~/.local/bin isn't on your PATH; add this line to your shell profile (~/.zshrc or ~/.bashrc) to use \`pylzr\`:"
           # shellcheck disable=SC2016  # printed for the user to copy, not expanded here
           say '    export PATH="$HOME/.local/bin:$PATH"' ;;
    esac
}

install_launchers_mac() {
    local dir="$1"
    local exe="$dir/.venv/bin/pylzr"
    # A tiny app, so macOS asks for the microphone for "PyLZR" (not for Terminal)
    mkdir -p "$(dirname "$MAC_APP")"
    rm -rf "$MAC_APP"
    local escaped="${exe//\\/\\\\}"
    escaped="${escaped//\"/\\\"}"
    osacompile -o "$MAC_APP" -e "do shell script quoted form of \"$escaped\" & \" > /dev/null 2>&1 &\""
    local plist="$MAC_APP/Contents/Info.plist"
    plutil -replace CFBundleIdentifier -string 'io.github.oh-ok-i-get-it.pylzr' "$plist"
    plutil -replace CFBundleName -string 'PyLZR' "$plist"
    plutil -replace NSMicrophoneUsageDescription \
        -string 'PyLZR listens to the audio input to react to the music.' "$plist"
    # Editing Info.plist breaks the app's signature; re-sign it (ad hoc)
    codesign --force --deep --sign - "$MAC_APP" >/dev/null 2>&1 || die "Couldn't re-sign $MAC_APP."
    say "  $MAC_APP"
    if [ -d "$(dirname "$DESKTOP_LINK")" ]; then
        ln -sfn "$MAC_APP" "$DESKTOP_LINK"
        say "  $DESKTOP_LINK"
    fi
}

install_launchers_linux() {
    local dir="$1"
    mkdir -p "$(dirname "$DESKTOP_FILE")"
    cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=PyLZR
Comment=Sound-reactive DMX laser controller
Exec="$dir/.venv/bin/pylzr"
Path=$dir
Terminal=false
Categories=AudioVideo;Audio;
EOF
    chmod +x "$DESKTOP_FILE"
    say "  $DESKTOP_FILE"
    if [ -d "$(dirname "$DESKTOP_LINK")" ]; then
        cp "$DESKTOP_FILE" "$DESKTOP_LINK"
        chmod +x "$DESKTOP_LINK"
        gio set "$DESKTOP_LINK" metadata::trusted true 2>/dev/null || true     # GNOME: allow launching
        say "  $DESKTOP_LINK"
    fi
    have update-desktop-database && update-desktop-database "$(dirname "$DESKTOP_FILE")" 2>/dev/null || true
}

install_launchers() {
    step 'Adding the app, Desktop shortcut and pylzr command'
    if [ "$OS" = Darwin ]; then install_launchers_mac "$1"; else install_launchers_linux "$1"; fi
    install_command "$1"
}

# --- Uninstall --------------------------------------------------------------

remove() {
    if [ -e "$1" ] || [ -L "$1" ]; then rm -rf "$1"; say "  removed $1"; fi
}

uninstall() {
    step 'Uninstalling PyLZR'
    if [ "$OS" = Darwin ]; then
        remove "$MAC_APP"
    else
        remove "$DESKTOP_FILE"
    fi
    remove "$DESKTOP_LINK"
    # Only our link, never someone else's `pylzr`
    if [ -L "$BIN_LINK" ] && case "$(readlink "$BIN_LINK")" in */.venv/bin/pylzr) true ;; *) false ;; esac; then
        remove "$BIN_LINK"
    fi
    cd "$HOME"                          # never delete the folder we're standing in
    remove "$APP_DIR"
    say ''
    ok 'PyLZR is uninstalled. uv, Python and system packages were left installed.'
    say "Your saved settings are kept in $SETTINGS_FILE (delete that folder to remove them)."
}

# --- Main -------------------------------------------------------------------

if $UNINSTALL; then
    uninstall
    exit 0
fi

resolve_folder
install_prerequisites
if $MANAGED; then update_code "$TARGET"; else step "Using PyLZR in $TARGET"; fi
sync_environment "$TARGET"
$LAUNCHERS && install_launchers "$TARGET"

say ''
ok 'PyLZR is installed.'
if $LAUNCHERS; then
    # shellcheck disable=SC2016  # the backticks below are literal text
    if [ "$OS" = Darwin ]; then
        say 'Start it from Applications or the Desktop (PyLZR), or type `pylzr` in a new terminal.'
    else
        say 'Start it from your app menu or the Desktop (PyLZR), or type `pylzr` in a new terminal.'
    fi
fi
say 'To update, run this installer again. To remove PyLZR, run it with --uninstall.'
