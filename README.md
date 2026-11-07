# OwlCap

A small low-latency player for USB HDMI capture cards on Linux, made for
playing consoles (e.g. a Nintendo Switch) on your PC and streaming them to
Discord with sound.

Video **and** audio run in a single GTK/GStreamer program. Because the audio
belongs to the same process as the window, the official Discord client sends
it along when you share the **OwlCap** window.

## Features

- Low-latency video: 1-frame queue, no A/V sync delay, GL-accelerated output
- Capture card audio played back through PipeWire/PulseAudio with small buffers
- Picks your capture card and its audio input automatically (MS2109-based cards and similar)
- Modes: 1080p60 MJPEG, 720p60 uncompressed (lowest latency), 1080p30 uncompressed, 1440p30 MJPEG
- Fullscreen with a HUD that appears when you move the mouse, so you can
  change settings without leaving fullscreen
- Volume and mute controls; remembers your last device, mode and volume

## Installation

### 1. Dependencies

**Arch / CachyOS / Manjaro**

```sh
sudo pacman -S python-gobject gtk3 gst-plugins-base gst-plugins-good gst-plugin-gtk v4l-utils libpulse
```

**Debian / Ubuntu**

```sh
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-gstreamer-1.0 \
    gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-gtk3 \
    gstreamer1.0-gl gstreamer1.0-pulseaudio v4l-utils pulseaudio-utils
```

**Fedora**

```sh
sudo dnf install python3-gobject gtk3 gstreamer1-plugins-base gstreamer1-plugins-good \
    gstreamer1-plugins-good-gtk v4l-utils pulseaudio-utils
```

### 2. Install

```sh
git clone https://github.com/ZeOwl/owlcap.git
cd owlcap
./install.sh
```

This links `owlcap` into `~/.local/bin` and adds **OwlCap** to your
app menu. Nothing is installed system-wide. `./uninstall.sh` removes it again.

You can also run it without installing: `./owlcap.py`

## Usage

1. Plug in the capture card and pick it under **Video** (usually preselected).
2. Pick the card's input under **Audio**, or "no audio".
3. Click **Start**.

| Key                 | Action            |
|---------------------|-------------------|
| F11 / double-click  | Toggle fullscreen |
| Esc                 | Leave fullscreen  |
| M                   | Toggle mute       |
| Space               | Start / stop      |

### Streaming to Discord

In Discord, share the **OwlCap** window (not the whole screen). The audio
is included automatically.

## Troubleshooting

- **No picture / error on start:** pick a different mode (720p60 uncompressed
  works on almost all cards), close other programs that use the card (OBS, VLC),
  or unplug and reconnect the HDMI source.
- **Black window or crashes with the GL output:** start with
  `OWLCAP_NO_GL=1 owlcap` to use the software renderer.
- **Discord stream freezes when the window is resized or leaves fullscreen
  (Hyprland):** this is a bug in `xdg-desktop-portal-hyprland`
  ([#445](https://github.com/hyprwm/xdg-desktop-portal-hyprland/issues/445)).
  Set the window size or fullscreen *before* you start the stream and use the
  fullscreen HUD to change settings. If it freezes, restart the stream in Discord.

Settings are stored in `~/.config/owlcap.json`.

## Acknowledgements

Built with the help of [Claude](https://claude.com/claude-code), Anthropic's AI
assistant, which helped with debugging, the fullscreen HUD and preparing the
project for release.

## License

[MIT](LICENSE)
