#!/bin/sh
set -eu
umask 077

case "${1:-area}" in
    area) set -- ;;
    full) set -- -window root ;;
    *) exit 2 ;;
esac

directory="$HOME/Pictures/Screenshots"
mkdir -p "$directory"
file="$directory/Screenshot-$(date +%Y-%m-%d_%H-%M-%S-%N).png"

# Bindings run on key release so the selection tool can grab the pointer.
# Drag to select a region, or click a window to capture it.
if ! /usr/bin/import -silent "$@" "$file"; then
    rm -f "$file"
    exit 1
fi

if [ ! -s "$file" ]; then
    rm -f "$file"
    exit 0
fi

# xclip stays in the background to serve the image to other applications.
if /usr/bin/xclip -selection clipboard -target image/png -i "$file" </dev/null >/dev/null 2>&1; then
    notify-send "Screenshot saved and copied" "$file" || true
else
    notify-send "Screenshot saved" "Clipboard copy failed. File: $file" || true
fi
