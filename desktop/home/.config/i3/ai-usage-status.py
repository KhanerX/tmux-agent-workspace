#!/usr/bin/env python3
"""Add subscription-wide weekly usage/reset blocks to the i3status stream."""

import argparse
from datetime import datetime
from html import escape
import json
import math
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import sys
import threading
import time


HOME = Path.home()
CACHE = Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache")) / "i3-ai-usage.json"
INTERVAL = 300
WEEK = 7 * 24 * 60 * 60
PROVIDERS = ("Codex",)


class UsageError(Exception):
    def __init__(self, message, retry=INTERVAL):
        super().__init__(message)
        self.retry = retry


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def codex_rate_limits():
    # Let Codex manage and refresh its own credentials instead of reusing an
    # access token from auth.json indefinitely. i3 may have a minimal PATH.
    executable = shutil.which("codex") or str(HOME / ".local/bin/codex")
    try:
        child = subprocess.Popen(
            [executable, "app-server", "--stdio"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, bufsize=0,
        )
    except FileNotFoundError:
        raise UsageError("codex missing") from None
    except OSError:
        raise UsageError("unavailable") from None

    deadline = time.monotonic() + 45
    pending = b""

    def send(message):
        child.stdin.write((json.dumps(message) + "\n").encode())

    def request(selector, request_id, method, params=None):
        nonlocal pending
        message = {"id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        send(message)
        while True:
            if time.monotonic() >= deadline:
                raise UsageError("timed out")
            if b"\n" not in pending:
                if not selector.select(max(0, deadline - time.monotonic())):
                    raise UsageError("timed out")
                chunk = os.read(child.stdout.fileno(), 65536)
                if not chunk:
                    raise UsageError("unavailable")
                pending += chunk
                continue
            line, pending = pending.split(b"\n", 1)
            if not line.strip():
                continue
            reply = json.loads(line)
            if reply.get("id") != request_id:
                continue
            if "error" in reply:
                # Never put raw server errors or credentials in the cache/bar.
                error = str(reply["error"].get("message", "")).lower()
                if any(word in error for word in (
                    "401", "unauthorized", "sign in", "login", "refresh token",
                    "authentication", "not authenticated",
                )):
                    raise UsageError("sign in")
                if "429" in error or "too many requests" in error:
                    raise UsageError("rate limited", 900)
                raise UsageError("unavailable")
            return reply["result"]

    try:
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            request(selector, 1, "initialize", {
                "clientInfo": {"name": "i3_usage", "version": "1.0"},
            })
            send({"method": "initialized"})
            return request(selector, 2, "account/rateLimits/read")
    except OSError:
        raise UsageError("unavailable") from None
    finally:
        child.terminate()
        try:
            child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
        child.stdin.close()
        child.stdout.close()


def snapshot(percent, reset):
    percent = float(percent)
    if not math.isfinite(percent) or percent < 0:
        raise UsageError("invalid usage")
    if isinstance(reset, str):
        reset = datetime.fromisoformat(reset.replace("Z", "+00:00")).timestamp()
    if reset is not None:
        reset = float(reset)
        if not math.isfinite(reset):
            raise UsageError("invalid reset")
    return {"percent": percent, "reset": reset, "updated": time.time()}


def fetch_codex():
    data = codex_rate_limits()
    limits = (data.get("rateLimitsByLimitId") or {}).get("codex") or data["rateLimits"]
    # Some plans put the weekly limit in primary, others in secondary.
    for key in ("primary", "secondary"):
        window = limits.get(key) or {}
        if window.get("windowDurationMins") == WEEK // 60:
            return snapshot(window["usedPercent"], window.get("resetsAt"))
    raise UsageError("no weekly limit")


def refresh_one(previous, force=False):
    now = time.time()
    if not force and previous.get("next_fetch", 0) > now:
        return previous
    try:
        value = fetch_codex()
        return {**value, "next_fetch": now + INTERVAL}
    except (UsageError, AttributeError, KeyError, TypeError, ValueError) as error:
        message = str(error) if isinstance(error, UsageError) else "invalid response"
        retry = getattr(error, "retry", INTERVAL)
        return {**previous, "error": message, "next_fetch": now + retry}


def refresh(state, force=False):
    result = {"Codex": refresh_one(state.get("Codex", {}), force)}
    if result == state:
        return result
    # Cache contains only percentages, reset timestamps and sanitized errors.
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        temporary = CACHE.with_name(f"{CACHE.name}.{os.getpid()}.tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(result, stream)
        os.replace(temporary, CACHE)
    except OSError:
        pass
    return result


def countdown(reset, now):
    seconds = reset - now
    if seconds <= 0:
        return "reset due"
    if seconds < 86400:
        return "in <1 day"
    days = math.ceil(seconds / 86400)
    return f"in {days} day{'s' if days != 1 else ''}"


def blocks(state, now=None):
    now = time.time() if now is None else now
    result = []
    for name in PROVIDERS:
        percentage = None
        value = state.get(name, {})
        reset = value.get("reset")
        expired = reset is not None and reset <= now
        stale = bool(value.get("error")) or now - value.get("updated", 0) > INTERVAL * 2
        if "percent" not in value or expired:
            reason = "reset due" if expired else value.get("error", "loading")
            text = short = f"{name} -- ({reason})"
        else:
            remaining_percent = max(0, 100 - value["percent"])
            percentage = f"{remaining_percent:g}%"
            color = "#05ffa1" if remaining_percent > 50 else "#f9f871" if remaining_percent > 20 else "#ff2a6d"
            text = short = f"{name} {percentage} left,"
            if reset is not None:
                local = datetime.fromtimestamp(reset).astimezone()
                reset_time = local.strftime("%-I:%M %p")
                remaining = countdown(reset, now)
                text += f" Resets {reset_time} {remaining}"
                short += f" {reset_time} {remaining}"
            else:
                text += " Reset not scheduled"
                short += " No reset"
            if stale:
                text += " [stale]"
                short += " [stale]"
        text, short = escape(text), escape(short)
        if percentage is not None:
            colored = f'<span foreground="{color}">{percentage}</span>'
            text = text.replace(percentage, colored, 1)
            short = short.replace(percentage, colored, 1)
        result.append({"name": "ai_usage", "instance": name.lower(), "full_text": text,
                       "short_text": short, "markup": "pango", "separator_block_width": 18})
    return result


def run_bar():
    state = read_json(CACHE)
    stopped = threading.Event()

    def worker():
        nonlocal state
        while not stopped.is_set():
            state = refresh(state)
            stopped.wait(5)

    threading.Thread(target=worker, daemon=True).start()
    child = subprocess.Popen(
        ["i3status", "-c", str(HOME / ".config/i3status/config")],
        stdout=subprocess.PIPE, text=True,
    )

    def stop(_signum, _frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    # Keep polling while i3bar is hidden, and resume output immediately afterward.
    signal.signal(signal.SIGUSR1, signal.SIG_IGN)
    signal.signal(signal.SIGUSR2, signal.SIG_IGN)
    try:
        print(json.dumps({"version": 1, "stop_signal": 0, "cont_signal": 0}), flush=True)
        print("[", flush=True)
        first = True
        for line in child.stdout:
            payload = line.strip().lstrip(",")
            if not payload.startswith("[") or payload == "[":
                continue
            original = json.loads(payload)
            print(("" if first else ",") + json.dumps(blocks(state) + original), flush=True)
            first = False
    finally:
        stopped.set()
        child.terminate()
        try:
            child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="print usage blocks as JSON and exit")
    parser.add_argument("--refresh", action="store_true", help="with --once, bypass the five-minute cache")
    args = parser.parse_args()
    try:
        if args.once:
            print(json.dumps(blocks(refresh(read_json(CACHE), args.refresh)), indent=2))
        else:
            run_bar()
    except BrokenPipeError:
        sys.exit(0)
