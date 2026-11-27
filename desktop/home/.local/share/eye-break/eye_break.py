#!/usr/bin/python3
"""A focus-free, click-to-dismiss X11 eye-rest reminder for i3."""

import argparse
import json
import math
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import time

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo
from battery_watch import alert_level, read_battery, recovered


def theme():
    """Read the live i3 palette again at each break (including theme switches)."""
    palette = dict(font="DejaVu Sans Mono", background="#05000a",
                   foreground="#f4f7ff", accent="#00d9ff", secondary="#c792ea")
    try:
        source = (Path.home() / ".config/i3/theme.conf").read_text()
        font = re.search(r"font\s+pango:(.+?)\s+\d+(?:\.\d+)?\s*$", source, re.M)
        if font:
            palette["font"] = font[1]
        for key, entry in [("background", "background"), ("foreground", "statusline"),
                           ("accent", "focused_workspace"), ("secondary", "separator")]:
            match = re.search(r"^\s*" + entry + r"\s+(#[0-9a-fA-F]{6})", source, re.M)
            if match:
                palette[key] = match[1]
    except OSError:
        pass
    return palette


def color(ctx, hex_color, alpha=1):
    ctx.set_source_rgba(*(int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)), alpha)


class Reminder:
    def __init__(self, interval=1200, duration=60, preview=False):
        self.interval, self.duration, self.preview = interval, duration, preview
        self.next_break = time.monotonic() + interval
        self.deadline = None
        self.last_tick = time.monotonic()
        self.palette = theme()
        self.overlay_kind = "eyes"
        self.battery = {}
        self.battery_notified_level = 0
        self.battery_error = False
        self.window = Gtk.Window(type=Gtk.WindowType.POPUP)
        self.window.set_title("Eye Break")
        self.window.set_wmclass("eye-break", "EyeBreak")
        self.window.set_decorated(False)
        self.window.set_accept_focus(False)
        self.window.set_focus_on_map(False)
        self.window.set_skip_taskbar_hint(True)
        self.window.set_skip_pager_hint(True)
        self.window.set_keep_above(True)
        self.window.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
        self.window.set_app_paintable(True)
        screen = self.window.get_screen()
        visual = screen.get_rgba_visual()
        if visual is None or not screen.is_composited():
            raise RuntimeError("Eye Break requires an RGBA visual and a compositor (picom).")
        self.window.set_visual(visual)
        self.window.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.window.connect("button-press-event", lambda *_: self.dismiss())
        self.window.connect("draw", self.draw)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self.quit)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self.quit)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, self.trigger)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR2, self.dismiss)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGHUP, self.battery_test)
        Gdk.Display.get_default().connect("closed", lambda *_: self.quit())
        GLib.timeout_add(100, self.tick)
        if not preview:
            GLib.timeout_add_seconds(15, self.check_battery)
            GLib.idle_add(self.initial_battery_check)
        if preview:
            self.trigger()
        else:
            print(f"Ready: {duration:g}s eye break every {interval:g}s.", flush=True)

    def position(self):
        display = Gdk.Display.get_default()
        _, x, y = display.get_default_seat().get_pointer().get_position()
        try:
            result = subprocess.run(["i3-msg", "-t", "get_workspaces"],
                                    capture_output=True, text=True, timeout=2, check=True)
            focused = next(w for w in json.loads(result.stdout) if w["focused"])
            rect = focused["rect"]
            x, y = rect["x"] + rect["width"] // 2, rect["y"] + rect["height"] // 2
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, StopIteration):
            pass
        rect = display.get_monitor_at_point(x, y).get_geometry()
        self.window.move(rect.x, rect.y + rect.height - rect.height // 2)
        self.window.resize(rect.width, rect.height // 2)

    def trigger(self):
        if self.deadline is None:
            self.overlay_kind = "eyes"
            self.palette = theme()
            self.position()
            self.deadline = time.monotonic() + self.duration
            self.next_break = time.monotonic() + self.interval
            self.window.show_all()
            self.window.get_window().raise_()
            print("Break started.", flush=True)
        return GLib.SOURCE_CONTINUE

    def initial_battery_check(self):
        self.check_battery()
        return GLib.SOURCE_REMOVE

    def check_battery(self):
        try:
            self.battery = read_battery()
            self.battery_error = False
        except GLib.Error as error:
            if not self.battery_error:
                print(f"Battery reading unavailable; will retry: {error}", flush=True)
                self.battery_error = True
            return GLib.SOURCE_CONTINUE
        self.update_battery(self.battery)
        return GLib.SOURCE_CONTINUE

    def update_battery(self, battery):
        self.battery = battery
        if recovered(battery):
            self.battery_notified_level = 0
            if self.overlay_kind == "battery" and self.deadline is not None:
                self.dismiss()
        level = alert_level(battery)
        if level > self.battery_notified_level:
            self.battery_notified_level = level
            self.show_battery()

    def show_battery(self, test=False):
        # Critical power warnings replace an eye break rather than overlap it.
        self.overlay_kind = "battery-test" if test else "battery"
        self.palette = theme()
        self.position()
        self.deadline = time.monotonic() + 15 if test else math.inf
        self.window.show_all()
        self.window.get_window().raise_()
        print("Battery alert shown" + (" (test)." if test else "."), flush=True)

    def battery_test(self):
        # Never replace a real critical alert with an expiring test.
        if self.overlay_kind != "battery" or self.deadline is None:
            self.show_battery(test=True)
        return GLib.SOURCE_CONTINUE

    def dismiss(self):
        self.window.hide()
        self.deadline = None
        if self.preview:
            Gtk.main_quit()
        print("Break finished.", flush=True)
        return GLib.SOURCE_CONTINUE

    def quit(self):
        self.window.destroy()
        Gtk.main_quit()
        return GLib.SOURCE_REMOVE

    def tick(self):
        now = time.monotonic()
        # A stalled desktop gets a fresh interval instead of an overdue reminder.
        if now - self.last_tick > 120:
            if self.deadline is not None:
                self.dismiss()
            self.next_break = now + self.interval
        self.last_tick = now
        if self.deadline is not None:
            if now >= self.deadline:
                self.dismiss()
            else:
                self.window.queue_draw()
        elif now >= self.next_break:
            self.trigger()
        return GLib.SOURCE_CONTINUE

    def text(self, ctx, message, size, y, ink, width, weight=Pango.Weight.NORMAL):
        layout = PangoCairo.create_layout(ctx)
        font = Pango.FontDescription()
        font.set_family(self.palette["font"])
        font.set_absolute_size(size * Pango.SCALE)
        font.set_weight(weight)
        layout.set_font_description(font)
        layout.set_text(message, -1)
        tw, th = layout.get_pixel_size()
        ctx.move_to((width - tw) / 2, y - th / 2)
        color(ctx, ink)
        PangoCairo.show_layout(ctx, layout)

    def draw(self, widget, ctx):
        w, h = widget.get_allocated_width(), widget.get_allocated_height()
        p = self.palette
        ctx.set_operator(cairo.OPERATOR_SOURCE)
        color(ctx, p["background"], 0.45)
        ctx.paint()
        ctx.set_operator(cairo.OPERATOR_OVER)
        if self.overlay_kind.startswith("battery"):
            test = self.overlay_kind == "battery-test"
            seconds = self.battery.get("TimeToEmpty", 0)
            percent = self.battery.get("Percentage", 0)
            estimate = (f"~{max(1, math.ceil(seconds / 60))} min remaining"
                        if seconds > 0 else f"{percent:.0f}% battery remaining")
            self.text(ctx, "Plug in your charger", 30, h / 2 - 20,
                      p["foreground"], w)
            self.text(ctx, "Battery alert · test" if test else estimate, 18,
                      h / 2 + 25, p["secondary"], w)
            return False
        remaining = max(0, (self.deadline or time.monotonic()) - time.monotonic())
        seconds = math.ceil(remaining)
        self.text(ctx, f"{seconds // 60:02d}:{seconds % 60:02d}", 36, h / 2,
                  p["foreground"], w, Pango.Weight.LIGHT)
        return False


def positive(value):
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError("must be a finite positive number")
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", action="store_true", help="show one break immediately, then exit")
    parser.add_argument("--interval", type=positive, default=1200, help="seconds between break starts")
    parser.add_argument("--duration", type=positive, default=60, help="break length in seconds")
    args = parser.parse_args()
    if args.interval <= args.duration:
        parser.error("interval must be longer than duration")
    Reminder(args.interval, args.duration, args.preview)
    if not args.preview and os.environ.get("NOTIFY_SOCKET"):
        address = os.environ["NOTIFY_SOCKET"]
        if address.startswith("@"):
            address = "\0" + address[1:]
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as notifier:
            notifier.connect(address)
            notifier.sendall(b"READY=1")
    Gtk.main()
