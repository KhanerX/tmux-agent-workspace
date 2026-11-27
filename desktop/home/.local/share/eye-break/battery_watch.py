"""Read the system's aggregate laptop battery estimate from UPower."""
from gi.repository import Gio, GLib


def read_battery():
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    result = bus.call_sync(
        "org.freedesktop.UPower", "/org/freedesktop/UPower/devices/DisplayDevice",
        "org.freedesktop.DBus.Properties", "GetAll",
        GLib.Variant("(s)", ("org.freedesktop.UPower.Device",)),
        GLib.VariantType.new("(a{sv})"), Gio.DBusCallFlags.NONE, 1500, None,
    )
    return result.unpack()[0]


def alert_level(battery):
    # State 2 = discharging. Never warn while plugged in and charging.
    if not battery.get("IsPresent") or battery.get("State") != 2:
        return 0
    remaining = battery.get("TimeToEmpty", 0)
    percent = battery.get("Percentage", 100)
    warning = battery.get("WarningLevel", 0)
    if warning >= 5 or 0 < remaining <= 60 or (remaining <= 0 and percent <= 2):
        return 2
    if warning >= 4 or 0 < remaining <= 180 or (remaining <= 0 and percent <= 5):
        return 1
    return 0


def recovered(battery):
    return (not battery.get("IsPresent") or battery.get("State") != 2
            or (battery.get("TimeToEmpty", 0) > 240
                and battery.get("Percentage", 100) > 7))
