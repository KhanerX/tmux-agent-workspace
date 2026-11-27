# Set up the desktop on a new Ubuntu laptop

From the new laptop, install Git, clone the repo, and run the desktop installer
**as your normal user**:

```sh
sudo apt update
sudo apt install git
git clone https://github.com/KhanerX/tmux-agent-workspace.git
cd tmux-agent-workspace
xargs -a desktop/packages.txt sudo apt install -y
sudo apt install network-manager-applet || sudo apt install network-manager-gnome
sh install.sh --desktop
systemctl --user daemon-reload
i3 -C -c "$HOME/.config/i3/config"
```

Log out. At the Ubuntu login screen, select your user, choose **i3** from the
session menu, and sign in. This is an X11 desktop; you can switch back to Ubuntu
from the same menu. **Alt+Enter** opens Kitty directly in tmux, **Alt+d** opens
Rofi, **Print** selects a screenshot and copies it, and **Shift+Print** captures
the full desktop. The keyboard map includes English (US) and Persian.

The installer copies the tmux setup and the files in [`files.txt`](files.txt).
Each replaced file gets a `.backup-…` sibling. Add `~/bin` and `~/.local/bin`
to your shell's `PATH` if needed. See the [main README](../README.md) for
tmux parking, session restore, and optional agent attention hooks.

### Personalize this laptop

- **Monitors and touchpad:** create `~/.config/i3/local-startup.sh` for startup
  commands specific to this machine. i3 runs it at login; reinstalling won't
  replace it. Use `xrandr --query` and `xinput list` to find *this* laptop's
  output and device names. Put any browser startup command here too.
- **Wallpaper:** copy the images you want into `~/Pictures/wallpaper/` and add
  `nitrogen --random --set-zoom-fill "$HOME/Pictures/wallpaper/"` to that script
  after your monitor commands.
- **Theme:** the dark palette is installed by default. Run
  `~/.local/bin/apply-unified-theme light` or `dark` to switch the i3 bar,
  i3status and Kitty palette. Open a new Kitty window for its updated colors.
- **Eye breaks:** the reminder starts with i3 and uses the picom user service.
  Run `~/.local/bin/eye-break now` to try it or `~/.local/bin/eye-break stop`
  to pause it. For startup errors, see `journalctl --user -u eye-break -u picom`.
- **Usage bar:** the battery, network and other i3status blocks work without an
  agent account. Install the Codex CLI and run `codex login` on this laptop to
  add your weekly usage. Credentials and usage caches aren't installation files.
- **Shell:** `.p10k.zsh` contains the prompt settings. To use them, install Zsh,
  [Oh My Zsh](https://github.com/ohmyzsh/ohmyzsh) and its
  [Powerlevel10k theme](https://github.com/romkatv/powerlevel10k#oh-my-zsh).
  In `~/.zshrc`, set `ZSH_THEME="powerlevel10k/powerlevel10k"` and
  `plugins=(sudo git)` before sourcing Oh My Zsh; add `source ~/.p10k.zsh`
  afterwards. Use `chsh -s "$(command -v zsh)"` and log in again to make it
  the shell in new tmux sessions.
- **Neovim (optional):** on a fresh Neovim install, copy the two files from
  [`optional/nvim`](optional/nvim) to `~/.config/nvim/`. Neovim bootstraps its
  plugins on first launch; the lockfile records the plugin revisions.
