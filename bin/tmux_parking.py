"""Shared naming for detached, per-session tmux parking lots."""


def parking_name(session):
    return "__parking_" + session.encode().hex()
