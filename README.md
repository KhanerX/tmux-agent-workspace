# tmux agent workspace

A small, plugin-manager-free tmux setup for working across several projects and
terminal AI agents. Keep active work in the tab bar, park background windows
without stopping them, see which agents need attention, and save enough metadata
to reopen your workspace later.

Built around **tmux + Python's standard library**, with optional Claude Code and
OpenCode integrations. Extracted from a daily-driver setup, with personal paths,
project names, and runtime state left out.

## The mental model

- **Session:** one workspace.
- **Window:** a project/task (the “tab” in tmux's status bar).
- **Pane:** a shell or agent inside a window.
- **Parking lot:** a detached session holding live windows you do not currently
  want in your tab bar. Parking moves the whole window; it does not pause it.
- **Attention marker:** a red `●` beside a window name when an agent finishes,
  fails, or needs input. Selecting that window acknowledges it; another agent
  turn also clears it. The marker is per window, not per pane.
- **Snapshot:** local JSON containing window names, pane directories, and agent
  conversation IDs. It is a reopening recipe, **not** a process checkpoint or a
  backup of the agents' conversation databases.

The status bar stays green, the selected window is bold, mouse support is on,
escape delay is zero, extended keys are enabled, and scrollback is 100,000 lines.

## Requirements

- **Linux** for save/load's `/proc`-based process detection.
- **tmux 3.4** is the tested version; older versions may lack config options.
- **Python 3.9+**, with no third-party Python packages.
- A POSIX shell and standard Linux utilities for installation.
- Optional: Claude Code and/or **OpenCode V2** installed and authenticated.
- Optional: `notify-send` for desktop notifications; `canberra-gtk-play` for sound.
  A working graphical notification/session bus is needed; remote/headless shells
  still get tmux markers. On Debian/Ubuntu the optional packages are
  `libnotify-bin` and `gnome-session-canberra`.

No TPM, tmux-resurrect, sudo, or background daemon is required. Other platforms
may support the config and parking, but are not tested; AI lookup is Linux-only.

## Install

```sh
git clone https://github.com/KhanerX/tmux-agent-workspace.git
cd tmux-agent-workspace
sh install.sh
```

This copies `tmux-save`, `tmux-load`, `tmux-park`, and their two Python modules to
`~/bin`, and `tmux-agent-status` to `~/.local/bin`. Existing destination files get
timestamped backups beside them. It does **not** change your shell, tmux config,
agent settings, or running sessions by default.

Add this to your shell startup file if these directories are not already on PATH:

```sh
export PATH="$HOME/bin:$HOME/.local/bin:$PATH"
```

For a fresh setup, install the included tmux config (backs up any existing file):

```sh
sh install.sh --with-tmux-config
tmux source-file ~/.tmux.conf  # only if a tmux server is already running
```

If you already have a customized config, **merge** `config/tmux.conf` instead of
replacing yours. The `after-select-window` hook acknowledges notifications; merge
it carefully if you already use that hook. Parking bindings assume helpers live
in `~/bin`. Reloading sets a global hook and global styles on your tmux server.

Keep `tmux_ai.py` and `tmux_parking.py` beside the Python executables when moving
them elsewhere. Restart your shell or re-source its startup file for PATH changes.

## Everyday tabs and panes

All bindings use tmux's default **prefix: `Ctrl-b`**, released before the next key.
If your config changes the prefix, use yours instead.

- Prefix, `c`: new window; prefix, `,`: rename it.
- Prefix, `n` / `p`: next / previous window (**this setup overrides `p` below**).
  Use prefix, `n`, a window number, or prefix, `w` to navigate instead.
- Prefix, `0`–`9`: select a numbered window; prefix, `w`: window/session picker.
- Prefix, `%`: split side-by-side; prefix, `"`: split top/bottom.
- Prefix, arrow key: change pane; prefix, `z`: toggle pane zoom.
- Prefix, `d`: detach without stopping anything.
- Prefix, `P` (**Shift-p**): park the current window.
- Prefix, `p` (**lowercase**): open the parking menu; choose a row to bring it back.

Optionally source `examples/project-tabs.sh` from Bash/Zsh and run:

```sh
project-tab ~/dev/my-project
```

This changes the current pane's directory, renames the **current** window, adds
a right-hand pane taking 33% of its width in the same directory, and focuses the
left pane. It does not create a new window; use prefix, `c` first if desired.

### Parking from the command line

```sh
tmux-park                         # park current window
tmux-park list                    # window IDs and names in this session's lot
tmux-park menu                    # interactive unpark picker
tmux-park unpark @42              # replace @42 with an ID from `list`
tmux-park list --session work     # explicitly choose the owning session
```

Each session has its own lot named `__parking_` plus the hex-encoded session name.
When parking the last visible window, a replacement shell keeps the main session
alive. Unparking moves the live window back and selects it. Do not rename or use
the internal parking sessions as normal workspaces. Parked processes still use
CPU/memory, and shutdown still terminates them.

## Save and restore

Run inside tmux, or specify a session explicitly:

```sh
tmux-save
tmux-save --session work --out ~/.work.snapshot.json

tmux-load --dry-run
tmux-load
tmux-load --file ~/.work.snapshot.json --session work --dry-run
tmux-load --file ~/.work.snapshot.json --session work
```

The default snapshot is `~/.tmux-ai-sessions.json`; a previous version is kept at
the same path with `.bak` appended. New snapshots are created with owner-only
permissions. One default file means saving another session replaces the previous
snapshot: use separate `--out` / `--file` paths for separate workspaces.

**Saving is read-only with respect to running panes:** it queries tmux and local
process/session metadata without sending keystrokes. Both visible and parked
windows are included. It discovers Claude sessions using open file descriptors,
unique title matches, and resume arguments; OpenCode lookup uses the installed
`opencode session list` CLI, unique titles, and resume arguments. It deliberately
does not guess “the newest conversation in this directory.”

**Loading** uses the current session by default (or the saved session name when
no current session can be found). It creates a detached session if needed,
reopens pane directories, and launches `claude --resume ID` or
`opencode --session ID` in interactive shells. Restored parked windows go into the
target session's parking lot. Attach with `tmux attach -t work` if needed.

Existing windows are matched by **name**, including the parking lot, and skipped
by default. Give windows unique names. To restart saved agents in matching panes
that are still idle shells in the same directory:

```sh
tmux-load --resume-existing --dry-run
tmux-load --resume-existing
```

That opt-in mode sends the resume command and Enter to eligible existing panes;
it is not intended for busy shells. Always inspect the dry run first.

### What restore does not do

- It does not restore shell history, scrollback, environment variables, arbitrary
  commands, in-memory processes, editors, or running servers.
- It stores original window indices and layouts, but currently creates windows
  at available indices and extra panes with horizontal splits; **the exact layout
  is not reapplied**. Active panes/windows are reselected where possible.
- Agents' local session histories must still exist. Copying JSON to another
  computer does not copy those histories, installed tools, or project files.
- Missing directories or clients can cause restore failures. Unresolved Claude
  IDs fall back to `claude --resume` (its picker); unresolved OpenCode IDs launch
  a new `opencode` invocation. Review warnings and the dry run before restoring.
- Lookup depends on agent CLI behavior and local metadata formats, which can
  change. Unknown tools are restored as ordinary shells.
- `--dry-run` does not change panes, but still queries tmux and local agent
  metadata; an agent CLI may start its own background service during lookup.

## Agent attention notifications

`tmux-agent-status waiting` sets `@agent_waiting=1` on the calling pane's window,
plays an optional sound, and sends an optional desktop notification. Repeated
waiting events are deduplicated until acknowledged. `active` clears the marker.
Outside tmux the helper is a no-op. No network notification service is used.

Try it inside a tmux pane:

```sh
~/.local/bin/tmux-agent-status waiting
~/.local/bin/tmux-agent-status active
```

Notifications include the tmux session/window name, so they may be visible on
your desktop or lock screen. Selecting a window clears its marker immediately,
even if another pane in that window still needs attention.

### Claude Code

Merge the **hooks only** from `integrations/claude/hooks.json` into
`~/.claude/settings.json`. Do not replace your whole settings file or remove
existing hooks. The example uses `$HOME`, not a machine-specific absolute path,
and does not change models, permissions, authentication, or enabled plugins.

Events wired up:

- `UserPromptSubmit` → active.
- `Stop`, `StopFailure` → waiting.
- `Notification` for idle/input/completion/permission events → waiting.

Restart Claude Code after merging. Hook availability varies with the installed
Claude Code version; if it rejects an event, check that version's hook reference.

### OpenCode V2

Copy the **directory**, including both files:

```sh
mkdir -p ~/.config/opencode/plugins
cp -R integrations/opencode/tmux-agent-status ~/.config/opencode/plugins/
```

Back up an existing plugin directory first. With a custom `XDG_CONFIG_HOME`, use
`$XDG_CONFIG_HOME/opencode/plugins` instead. Restart the TUI after installing.
Global local plugins are auto-loaded; no personal OpenCode config is included.

- `server.ts` is the minimal server entrypoint.
- `tui.ts` runs inside the terminal UI so it has the correct `TMUX_PANE`.
- Busy events clear attention; idle, permission, and question events request it.
- Session routing/tab checks filter shared-server events to the TUI's sessions;
  at a non-session route, the plugin also accepts events as a fallback. The
  filtering is best-effort, not a security boundary.

The plugin uses the OpenCode V2 `@opencode/plugin` SDK and its Bun runtime, not
the V1 plugin API. No separate npm install is needed for the Python/tmux tools.
See the [V2 plugin docs](https://opencode.ai/v2/docs/build/plugins) for loading and
SDK compatibility if your OpenCode release changes these interfaces.

## Privacy and safe sharing

This repository contains **code, a tmux config, and sanitized examples only**.
It intentionally excludes snapshots/backups, transcripts, credentials, shell
history, personal project shortcuts, and full agent configuration files.

Your **generated** snapshots are private: they contain absolute project paths,
pane/window titles, and conversation identifiers. Keep them out of Git and review
them before sharing. `.gitignore` is a safety net for the default snapshot names,
`*.snapshot.json`, and JSONL transcripts, not a guarantee for arbitrary filenames.
Never load an untrusted snapshot: restore launches commands and agents using its
contents. No telemetry or external notification endpoint is added by these tools.

## Checks and troubleshooting

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q bin
```

Tests use a separate tmux socket and temporary HOME, never your live workspace.
The Python suite has no external dependencies; tmux is needed for integration
tests. Agent integrations require manual end-to-end checking in their clients.

- **Parking shortcut does nothing:** verify `~/bin/tmux-park` is executable and
  reload your tmux config. Prefix, `p` now means parking, not previous-window.
- **No desktop popup/sound:** test the helper directly; verify optional utilities
  and your graphical session's D-Bus environment. The tmux dot works without them.
- **No dot:** check the config was loaded and hooks/plugin are installed. `tmux
  show-option -wqv @agent_waiting` shows the current window's marker.
- **Wrong/missing agent resume:** use unique titles, check local session histories,
  inspect save warnings, and do not delete the originals until restore is verified.
- **No automatic saving:** intentional. Run `tmux-save` before rebooting; no cron
  job, timer, or automatic shutdown hook is installed by this repository.

To uninstall, remove only the installed files you selected above, remove the
merged hooks/plugin/config lines, and restore any timestamped backups you need.
Do not kill parking sessions unless you intend to terminate their processes.
