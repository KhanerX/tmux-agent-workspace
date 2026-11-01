# Source this from ~/.bashrc or ~/.zshrc. Usage: project-tab ~/dev/my-project
# A generic version of the original per-project tab helpers.
project-tab() {
  if [ -z "${TMUX-}" ] || [ "$#" -ne 1 ]; then
    echo 'Usage (inside tmux): project-tab /path/to/project' >&2
    return 1
  fi
  cd -- "$1" || return
  tmux rename-window "$(basename -- "$PWD")"
  tmux split-window -h -l 33% -c "$PWD"
  tmux select-pane -L
}
