#!/usr/bin/env python3
"""
OwlCap – a small low-latency player for HDMI capture cards.

Video AND audio run in ONE program (GStreamer). That way the audio belongs
to the same process as the window, and the official Discord client includes
it when you share the "OwlCap" window.

Controls:
  F11 / double-click  toggle fullscreen     Esc    leave fullscreen
  M                   toggle mute           Space  start/stop

Requires: python-gobject, GTK 3, GStreamer (base, good, gtk plugins), v4l-utils
"""
import json
import os
import subprocess
from pathlib import Path

import gi

gi.require_version("Gst", "1.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gst, Gtk  # noqa: E402

Gst.init(None)

APP_NAME = "OwlCap"
CONFIG = Path.home() / ".config" / "owlcap.json"

# display name -> (width, height, fps, card format)
MODES = {
    "1080p60 (MJPEG, default)": (1920, 1080, 60, "mjpeg"),
    "720p60 uncompressed (lowest latency)": (1280, 720, 60, "yuyv"),
    "1080p30 uncompressed": (1920, 1080, 30, "yuyv"),
    "1440p30 (MJPEG)": (2560, 1440, 30, "mjpeg"),
}

HUD_TIMEOUT_MS = 2500  # how long the fullscreen HUD stays after the last mouse movement

HUD_CSS = b"""
.hud { background-color: rgba(20, 20, 20, 0.85); border-radius: 0 0 10px 10px; }
.hud label { color: #eeeeee; }
"""

KEYWORDS = ("usb3", "ms2109", "macrosilicon", "capture", "hdmi", "guermok", "video")

REQUIRED = {
    "v4l2src": "gst-plugins-good",
    "jpegdec": "gst-plugins-good",
    "pulsesrc": "gst-plugins-good",
    "pulsesink": "gst-plugins-good",
    "videoconvert": "gst-plugins-base",
    "audioconvert": "gst-plugins-base",
    "audioresample": "gst-plugins-base",
    "volume": "gst-plugins-base",
    "gtksink": "gst-plugin-gtk",
}


# ---------------------------------------------------------------- Devices
def run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def find_video_devices():
    """[(display name, /dev/videoX)] – only the first node per device."""
    devices, name, taken = [], None, False
    for line in run(["v4l2-ctl", "--list-devices"]).splitlines():
        if line and not line[0].isspace():
            name, taken = line.rstrip(":").split(" (")[0].strip(), False
        elif name and not taken and line.strip().startswith("/dev/video"):
            path = line.strip()
            devices.append((f"{name}  ({path})", path))
            taken = True
    if not devices:
        devices = [(str(p), str(p)) for p in sorted(Path("/dev").glob("video*"))]
    return devices


def find_audio_sources():
    out = []
    for line in run(["pactl", "list", "short", "sources"]).splitlines():
        parts = line.split("\t")
        if len(parts) > 1 and not parts[1].endswith(".monitor"):
            out.append(parts[1])
    return out


def pick_default(items, saved):
    if saved in items:
        return saved
    # keywords by priority; only match the name, not "(/dev/videoX)"
    for k in KEYWORDS:
        for item in items:
            if k in item.split("  (")[0].lower():
                return item
    return items[0] if items else None


def load_config():
    try:
        return json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        return {}


# ---------------------------------------------------------------- Video sink
def make_video_sink():
    """GL-accelerated GTK sink, else software sink. Returns (sink, widget)."""
    if not os.environ.get("OWLCAP_NO_GL"):
        gl = Gst.ElementFactory.make("gtkglsink", None)
        bin_ = Gst.ElementFactory.make("glsinkbin", None)
        if gl and bin_:
            gl.set_property("sync", False)
            bin_.set_property("sink", gl)
            return bin_, gl.get_property("widget")
    sink = Gst.ElementFactory.make("gtksink", None)
    if not sink:
        return None, None
    sink.set_property("sync", False)
    return sink, sink.get_property("widget")


# ---------------------------------------------------------------- App
class Player(Gtk.Window):
    def __init__(self):
        super().__init__(title=APP_NAME)
        self.set_default_size(1280, 800)
        self.set_icon_name("video-display")
        self.cfg = load_config()
        self.video_pipe = None
        self.audio_pipe = None
        self.volume = None
        self.video_sink = None
        self.is_fullscreen = False
        self.hud_timer = None
        self.last_pointer = None

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(root)
        self.root = root

        # --- Controls
        self.controls = Gtk.Grid(column_spacing=8, row_spacing=6, margin=8)
        root.pack_start(self.controls, False, False, 0)

        self.video_combo = Gtk.ComboBoxText(hexpand=True)
        self.audio_combo = Gtk.ComboBoxText(hexpand=True)
        self.mode_combo = Gtk.ComboBoxText()
        for m in MODES:
            self.mode_combo.append(m, m)
        self.mode_combo.set_active_id(self.cfg.get("mode") if self.cfg.get("mode") in MODES
                                      else next(iter(MODES)))

        self.start_btn = Gtk.Button(label="▶ Start")
        self.stop_btn = Gtk.Button(label="■ Stop", sensitive=False)
        refresh_btn = Gtk.Button(label="⟳ Devices")
        self.fs_btn = fs_btn = Gtk.Button(label="⛶ Fullscreen")
        self.start_btn.connect("clicked", lambda *_: self.start())
        self.stop_btn.connect("clicked", lambda *_: self.stop())
        refresh_btn.connect("clicked", lambda *_: self.refresh())
        fs_btn.connect("clicked", lambda *_: self.toggle_fullscreen())

        self.mute_check = Gtk.CheckButton(label="Mute")
        self.mute_check.set_active(self.cfg.get("muted", False))
        self.mute_check.connect("toggled", lambda *_: self.apply_volume())
        self.vol_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 150, 5)
        self.vol_scale.set_value(self.cfg.get("volume", 100))
        self.vol_scale.set_size_request(140, -1)
        self.vol_scale.connect("value-changed", lambda *_: self.apply_volume())

        def label(t):
            return Gtk.Label(label=t, xalign=0)

        c = self.controls
        c.attach(label("Video"), 0, 0, 1, 1)
        c.attach(self.video_combo, 1, 0, 3, 1)
        c.attach(label("Mode"), 4, 0, 1, 1)
        c.attach(self.mode_combo, 5, 0, 2, 1)
        c.attach(label("Audio"), 0, 1, 1, 1)
        c.attach(self.audio_combo, 1, 1, 3, 1)
        c.attach(label("Volume"), 4, 1, 1, 1)
        c.attach(self.vol_scale, 5, 1, 1, 1)
        c.attach(self.mute_check, 6, 1, 1, 1)
        btns = Gtk.Box(spacing=6)
        for b in (self.start_btn, self.stop_btn, refresh_btn, fs_btn):
            btns.pack_start(b, True, True, 0)
        c.attach(btns, 0, 2, 7, 1)

        # --- Video area
        self.video_box = Gtk.EventBox()
        self.video_box.override_background_color(Gtk.StateFlags.NORMAL, Gdk.RGBA(0, 0, 0, 1))
        self.video_box.connect("button-press-event", self.on_click)
        # The video widget stays in the stack permanently and is only switched –
        # removing the GL widget from the window crashes GTK.
        self.video_stack = Gtk.Stack()
        self.placeholder = Gtk.Label(label="Click “Start”")
        self.placeholder.override_color(Gtk.StateFlags.NORMAL, Gdk.RGBA(0.7, 0.7, 0.7, 1))
        self.video_stack.add_named(self.placeholder, "placeholder")
        self.video_box.add(self.video_stack)

        # --- Fullscreen HUD: sits on top of the video so showing/hiding it doesn't
        # change the window size (which would freeze a Discord window share)
        overlay = Gtk.Overlay()
        overlay.add(self.video_box)
        self.hud = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.CROSSFADE,
                                valign=Gtk.Align.START, halign=Gtk.Align.FILL)
        self.hud_box = Gtk.EventBox()
        self.hud_box.get_style_context().add_class("hud")
        self.hud.add(self.hud_box)
        overlay.add_overlay(self.hud)
        root.pack_start(overlay, True, True, 0)

        css = Gtk.CssProvider()
        css.load_from_data(HUD_CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        # --- Status bar
        self.status = Gtk.Label(label="Ready", xalign=0, margin=6)
        self.status.get_style_context().add_class("dim-label")
        root.pack_start(self.status, False, False, 0)

        self.add_events(Gdk.EventMask.POINTER_MOTION_MASK)
        self.video_box.add_events(Gdk.EventMask.POINTER_MOTION_MASK)
        self.connect("motion-notify-event", self.on_motion)
        self.connect("key-press-event", self.on_key)
        self.connect("window-state-event", self.on_window_state)
        self.connect("delete-event", self.on_close)

        self.refresh()
        self.show_all()
        self.check_plugins()

    # ---------- Helpers
    def set_status(self, text):
        self.status.set_text(text)

    def check_plugins(self):
        missing = sorted({pkg for el, pkg in REQUIRED.items()
                          if not Gst.ElementFactory.find(el)})
        if missing:
            self.error_dialog(
                "Missing GStreamer plugins",
                "Please install these packages (names may differ by distribution):\n\n"
                + " ".join(missing))
            self.start_btn.set_sensitive(False)

    def error_dialog(self, title, text):
        dlg = Gtk.MessageDialog(transient_for=self, modal=True,
                                message_type=Gtk.MessageType.ERROR,
                                buttons=Gtk.ButtonsType.OK, text=title)
        dlg.format_secondary_text(text)
        dlg.run()
        dlg.destroy()

    def refresh(self):
        self.video_map = dict(find_video_devices())
        self.video_combo.remove_all()
        for name in self.video_map:
            self.video_combo.append(name, name)
        default = pick_default(list(self.video_map), self.cfg.get("video", ""))
        if default:
            self.video_combo.set_active_id(default)

        self.audio_combo.remove_all()
        self.audio_combo.append("", "– no audio –")
        sources = find_audio_sources()
        for s in sources:
            self.audio_combo.append(s, s)
        self.audio_combo.set_active_id(pick_default(sources, self.cfg.get("audio_source", "")) or "")

        self.set_status("No capture card found – is it plugged in?"
                        if not self.video_map else "Ready")

    # ---------- Start / stop
    def start(self):
        self.stop()
        dev = self.video_map.get(self.video_combo.get_active_id() or "")
        if not dev:
            self.error_dialog("No video device", "Please select a capture card.")
            return
        w, h, fps, fmt = MODES[self.mode_combo.get_active_id()]

        # --- Video (create the sink only once and reuse it)
        if not self.video_sink:
            sink, widget = make_video_sink()
            if not sink:
                self.error_dialog("Missing plugin", "Please install gst-plugin-gtk.")
                return
            self.video_sink = sink
            self.video_stack.add_named(widget, "video")
            widget.show()
        sink = self.video_sink
        if fmt == "mjpeg":
            src = (f'v4l2src device="{dev}" ! image/jpeg,width={w},height={h},'
                   f'framerate={fps}/1 ! jpegdec')
        else:
            src = (f'v4l2src device="{dev}" ! video/x-raw,format=YUY2,width={w},'
                   f'height={h},framerate={fps}/1')
        desc = (f"{src} ! queue max-size-buffers=1 max-size-bytes=0 max-size-time=0 "
                f"leaky=downstream ! videoconvert name=vconv")
        try:
            self.video_pipe = Gst.parse_launch(desc)
        except GLib.Error as e:
            self.error_dialog("Video pipeline", str(e))
            return
        self.video_pipe.add(sink)
        self.video_pipe.get_by_name("vconv").link(sink)
        self.watch(self.video_pipe, "Video")
        self.video_stack.set_visible_child_name("video")

        # --- Audio (same process -> Discord includes it)
        asrc = self.audio_combo.get_active_id()
        if asrc:
            adesc = (f'pulsesrc device="{asrc}" buffer-time=20000 latency-time=5000 '
                     f'client-name="{APP_NAME}" ! audioconvert ! audioresample ! '
                     f'volume name=vol ! pulsesink buffer-time=40000 latency-time=10000 '
                     f'sync=false client-name="{APP_NAME}"')
            try:
                self.audio_pipe = Gst.parse_launch(adesc)
                self.volume = self.audio_pipe.get_by_name("vol")
                self.apply_volume()
                self.watch(self.audio_pipe, "Audio")
            except GLib.Error as e:
                self.audio_pipe = None
                self.set_status(f"Could not start audio: {e}")

        self.video_pipe.set_state(Gst.State.PLAYING)
        if self.audio_pipe:
            self.audio_pipe.set_state(Gst.State.PLAYING)

        self.start_btn.set_sensitive(False)
        self.stop_btn.set_sensitive(True)
        self.set_status(f"Running: {self.mode_combo.get_active_id()}"
                        + ("" if asrc else " – no audio"))
        self.save_config()

    def stop(self):
        self.video_stack.set_visible_child_name("placeholder")
        for pipe in (self.video_pipe, self.audio_pipe):
            if pipe:
                pipe.get_bus().remove_signal_watch()
                pipe.set_state(Gst.State.NULL)
        if self.video_pipe and self.video_sink.get_parent() == self.video_pipe:
            self.video_pipe.remove(self.video_sink)  # release it for the next start
        self.video_pipe = self.audio_pipe = self.volume = None
        self.start_btn.set_sensitive(True)
        self.stop_btn.set_sensitive(False)

    def watch(self, pipe, what):
        bus = pipe.get_bus()
        bus.add_signal_watch()
        bus.connect("message::error", self.on_error, what)

    def on_error(self, _bus, msg, what):
        err, _dbg = msg.parse_error()
        self.stop()
        hint = ""
        if what == "Video":
            hint = ("\n\nTips:\n• Pick a different mode (e.g. 720p60)\n"
                    "• Is the card still in use by VLC or another program?\n"
                    "• Unplug the HDMI source (e.g. take the Switch out of its dock) and reconnect it")
        self.set_status(f"{what} error: {err.message}")
        self.error_dialog(f"{what} error", err.message + hint)

    def apply_volume(self):
        if self.volume:
            self.volume.set_property("volume", self.vol_scale.get_value() / 100)
            self.volume.set_property("mute", self.mute_check.get_active())

    # ---------- Fullscreen / keys
    def toggle_fullscreen(self):
        if self.is_fullscreen:
            self.unfullscreen()
        else:
            self.fullscreen()

    def on_window_state(self, _w, event):
        fullscreen = bool(event.new_window_state & Gdk.WindowState.FULLSCREEN)
        if fullscreen == self.is_fullscreen:
            return
        self.is_fullscreen = fullscreen
        self.status.set_visible(not fullscreen)
        # move the controls between the window layout and the HUD
        self.controls.get_parent().remove(self.controls)
        if fullscreen:
            self.hud_box.add(self.controls)
            self.fs_btn.set_label("⛶ Exit fullscreen")
            self.show_hud()
        else:
            self.root.pack_start(self.controls, False, False, 0)
            self.root.reorder_child(self.controls, 0)
            self.fs_btn.set_label("⛶ Fullscreen")
            self.hide_hud()

    # ---------- HUD
    def pointer_pos(self):
        seat = self.get_display().get_default_seat()
        _win, x, y, _mask = self.get_window().get_device_position(seat.get_pointer())
        return x, y

    def on_motion(self, *_):
        if self.is_fullscreen:
            pos = self.pointer_pos()
            if pos != self.last_pointer:  # ignore phantom events without real movement
                self.last_pointer = pos
                self.show_hud()
        return False

    def show_hud(self):
        self.hud.set_reveal_child(True)
        self.get_window().set_cursor(None)
        if self.hud_timer:
            GLib.source_remove(self.hud_timer)
        self.hud_timer = GLib.timeout_add(HUD_TIMEOUT_MS, self.on_hud_timeout)

    def on_hud_timeout(self):
        # keep it visible while the mouse is over the HUD or a dropdown is open
        over_hud = self.pointer_pos()[1] <= self.hud.get_allocated_height()
        popup = any(cb.get_property("popup-shown")
                    for cb in (self.video_combo, self.audio_combo, self.mode_combo))
        if over_hud or popup:
            return True
        self.hud_timer = None
        self.hide_hud()
        if self.is_fullscreen:
            self.get_window().set_cursor(Gdk.Cursor.new_from_name(self.get_display(), "none"))
        return False

    def hide_hud(self):
        if self.hud_timer:
            GLib.source_remove(self.hud_timer)
            self.hud_timer = None
        self.hud.set_reveal_child(False)
        self.get_window().set_cursor(None)

    def on_click(self, _w, event):
        if event.type == Gdk.EventType._2BUTTON_PRESS:
            self.toggle_fullscreen()

    def on_key(self, _w, event):
        key = Gdk.keyval_name(event.keyval)
        if key == "F11":
            self.toggle_fullscreen()
        elif key == "Escape" and self.is_fullscreen:
            self.unfullscreen()
        elif key in ("m", "M"):
            self.mute_check.set_active(not self.mute_check.get_active())
        elif key == "space":
            self.stop() if self.video_pipe else self.start()
        else:
            return False
        return True

    # ---------- Settings
    def save_config(self):
        cfg = {
            "video": self.video_combo.get_active_id() or "",
            "audio_source": self.audio_combo.get_active_id() or "",
            "mode": self.mode_combo.get_active_id(),
            "volume": self.vol_scale.get_value(),
            "muted": self.mute_check.get_active(),
        }
        try:
            CONFIG.parent.mkdir(parents=True, exist_ok=True)
            CONFIG.write_text(json.dumps(cfg, indent=2))
        except OSError:
            pass

    def on_close(self, *_):
        self.save_config()
        self.stop()
        Gtk.main_quit()
        return False


if __name__ == "__main__":
    GLib.set_prgname("owlcap")
    GLib.set_application_name(APP_NAME)
    Player()
    Gtk.main()
