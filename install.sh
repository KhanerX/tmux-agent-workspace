#!/bin/sh
# Install only the selected files. No sudo, downloads, or automatic agent changes.
set -eu

with_config=false
case "${1-}" in
  '') ;;
  --with-tmux-config) with_config=true ;;
  *) echo "Usage: sh install.sh [--with-tmux-config]" >&2; exit 2 ;;
esac
[ "$#" -le 1 ] || { echo 'Too many arguments' >&2; exit 2; }

root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
backup=$(date +%Y%m%d-%H%M%S)-$$
install_file() {
  source=$1 destination=$2 mode=$3
  if [ -e "$destination" ] || [ -L "$destination" ]; then
    cp -p -- "$destination" "$destination.backup-$backup"
    echo "Backed up $destination -> $destination.backup-$backup"
    # Replace a symlink itself instead of writing through to its target.
    rm -- "$destination"
  fi
  install -m "$mode" -- "$source" "$destination"
  echo "Installed $destination"
}

mkdir -p "$HOME/bin" "$HOME/.local/bin"
for name in tmux-save tmux-load tmux-park; do
  install_file "$root/bin/$name" "$HOME/bin/$name" 755
done
for name in tmux_ai.py tmux_parking.py; do
  install_file "$root/bin/$name" "$HOME/bin/$name" 644
done
install_file "$root/bin/tmux-agent-status" "$HOME/.local/bin/tmux-agent-status" 755
if "$with_config"; then
  install_file "$root/config/tmux.conf" "$HOME/.tmux.conf" 644
fi
echo 'Done. Add ~/bin and ~/.local/bin to PATH; see README.md for config and agent hooks.'
