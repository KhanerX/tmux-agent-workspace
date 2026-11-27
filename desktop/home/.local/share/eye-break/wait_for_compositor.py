"""Wait until the compositor actually owns this display, not just a process ID."""
import time

import gi

gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib

screen = Gdk.Screen.get_default()
if screen is None:
    raise SystemExit("No X11 display available")
deadline = time.monotonic() + 15
context = GLib.MainContext.default()
while time.monotonic() < deadline:
    while context.pending():
        context.iteration(False)
    if screen.is_composited():
        raise SystemExit(0)
    time.sleep(0.1)
raise SystemExit("Compositor did not become ready on this display within 15 seconds")
