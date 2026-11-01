"""Session lookup shared by tmux-save and tmux-load."""
import functools
import json
import os
from pathlib import Path
import re
import subprocess
import sys

CLAUDE_PROJECTS = Path.home() / ".claude/projects"
UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")


def proc_args(pid):
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="replace").split("\0")
    except OSError:
        return []


def proc_stat(pid):
    # comm may contain spaces and parentheses; fields after it start at state.
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    except (OSError, IndexError):
        return []


def idle_shell(pid, command):
    if os.path.basename(command) not in ("sh", "bash", "zsh", "fish", "dash", "ksh"):
        return False
    fields = proc_stat(pid)
    # The shell, rather than a foreground job, must own the terminal.
    return len(fields) > 5 and fields[2] == fields[5]


def session_arg(pid, flags, pattern):
    args = proc_args(pid)
    for i, arg in enumerate(args):
        value = None
        if arg in flags and i + 1 < len(args):
            value = args[i + 1]
        elif any(arg.startswith(flag + "=") for flag in flags):
            value = arg.split("=", 1)[1]
        if value and re.fullmatch(pattern, value):
            return value
    return None


@functools.lru_cache(maxsize=None)
def claude_sessions(directory):
    """Read only title records, not prompts, from top-level transcripts."""
    project = CLAUDE_PROJECTS / re.sub(r"[^a-zA-Z0-9]", "-", directory)
    rows = []
    for path in project.glob("*.jsonl"):
        if not UUID.fullmatch(path.stem):
            continue
        titles = {}
        try:
            with path.open() as f:
                for line in f:
                    if '"ai-title"' not in line and '"custom-title"' not in line:
                        continue
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue
                    key = {"ai-title": "aiTitle", "custom-title": "customTitle"}.get(record.get("type"))
                    if key and record.get(key):
                        titles[key] = record[key]
            rows.append((path.stem, list(titles.values())))
        except OSError:
            continue
    return rows


def title_match(rows, title):
    """Require a unique exact match, or an explicitly truncated title prefix."""
    title = title.strip()
    if not title:
        return None
    matches = {sid for sid, titles in rows if title in titles}
    if not matches and title.endswith(("…", "...")):
        prefix = title.removesuffix("…").removesuffix("...").strip()
        if len(prefix) >= 15:
            matches = {sid for sid, titles in rows if any(t.startswith(prefix) for t in titles)}
    return next(iter(matches)) if len(matches) == 1 else None


def claude_title(title):
    return re.sub(r"^[✳✻✽✶✢·*]\s*", "", title or "").strip()


def resolve_claude(tool_pid, directory, pane_title=""):
    # An open task/transcript descriptor identifies the current session even
    # after an in-app switch, unlike the original --resume argument.
    try:
        for fd in Path(f"/proc/{tool_pid}/fd").iterdir():
            try:
                link = os.readlink(fd)
            except OSError:
                continue
            if "/claude-" in link or str(CLAUDE_PROJECTS) in link:
                match = UUID.search(link)
                if match:
                    return match.group(), "proc-fd"
    except OSError:
        pass
    sid = title_match(claude_sessions(directory), claude_title(pane_title))
    if sid:
        return sid, "title-match"
    sid = session_arg(tool_pid, ("--resume", "-r", "--session-id"), UUID.pattern)
    if sid:
        return sid, "proc-args"
    # Choosing the newest transcript is wrong when multiple panes share a cwd.
    return None, "not-found"


@functools.lru_cache(maxsize=None)
def opencode_sessions(directory):
    # Use the installed CLI so V2's service/database layout is respected.
    try:
        result = subprocess.run(
            ["opencode", "session", "list", "--format", "json", "--max-count", "10000"],
            cwd=directory, capture_output=True, text=True, check=True, timeout=30,
        )
        return [row for row in json.loads(result.stdout) if row.get("directory") == directory]
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"warn: opencode session lookup failed: {exc}", file=sys.stderr)
        return []


def resolve_opencode(directory, pane_title, tool_pid=None):
    rows = opencode_sessions(directory)
    title = re.sub(r"^OC\s*\|?\s*", "", pane_title or "").strip()
    sid = title_match([(r["id"], [r.get("title", "")]) for r in rows], title)
    if sid:
        row = next(r for r in rows if r["id"] == sid)
        return sid, "title-match", row.get("title")
    sid = session_arg(tool_pid, ("--session", "-s"), r"ses_[A-Za-z0-9]+")
    if sid:
        return sid, "proc-args", None
    return None, "not-found", None


def recover_pane(pane):
    """Repair old snapshots using positive title matches, never recency."""
    pane = dict(pane)
    tool = pane.get("tool", "shell")
    title = pane.get("pane_title", "")
    sid = pane.get("ai_session")
    if tool == "claude" and sid and UUID.fullmatch(sid.removesuffix(".")):
        pane["ai_session"] = sid.removesuffix(".")
    if tool == "claude" and (not sid or pane.get("method") == "latest-in-project-dir"):
        match = title_match(claude_sessions(pane["path"]), claude_title(title))
        if match:
            pane.update(ai_session=match, method="title-match-recovered")
    elif tool == "shell" and re.match(r"^[✳✻✽✶✢·*]\s*", title):
        match = title_match(claude_sessions(pane["path"]), claude_title(title))
        if match:
            pane.update(tool="claude", ai_session=match, method="title-match-recovered")
    elif tool == "shell" and re.match(r"^OC(?:\s|\|)", title):
        match, method, db_title = resolve_opencode(pane["path"], title)
        if match:
            pane.update(tool="opencode", ai_session=match, method=method, db_title=db_title)
    return pane
