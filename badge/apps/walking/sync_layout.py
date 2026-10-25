"""Pure texts and view model for the walking sync screens.

No badge globals, so every screen's wording and the confetti maths can be unit
tested on the laptop. MicroPython-compatible: plain functions and dicts only.

Rule for totals: before ``SUCCESS`` only the previous confirmed total
(``session.confirmed_total``) is ever shown. The new total comes from
``session.result_total`` and appears only in ``SUCCESS`` and ``SEPARATE``.
"""

import math

import layout
import sync

TITLE_WALKING = None  # the walking screen keeps the main screen's status line
TITLE_HOLD = "Holding steady"
TITLE_CONNECTING = "Connecting"
TITLE_EXCHANGE = "Swapping steps"
TITLE_AWAITING_ACK = "Waiting for acknowledgement"
TITLE_SYNCED = "Synced!"
TITLE_GOAL = "You made it!"
TITLE_SEPARATE = "Move badges apart"
TITLE_UP_TO_DATE = "Already up to date"
TITLE_RETRY = "Sync didn't finish"

HINTS = {
    sync.HOLD: "Keep badges back to back",
    sync.CONNECTING: "Stay close together",
    sync.EXCHANGE: "Keep holding",
    sync.AWAITING_ACK: "Almost there",
    sync.UP_TO_DATE: "Nothing new to share",
}

REASON_TEXT = {
    sync.REASON_DROPPED: "Badges moved apart too soon",
    sync.REASON_TIMEOUT: "Timed out",
}
REASON_DEFAULT = "Try again"

TOTAL_CAPTION = "of " + layout.format_count(layout.GOAL) + " shared steps"

# Confetti: deterministic, falls for CONFETTI_MS and fades out over the last
# CONFETTI_FADE_MS, comfortably inside sync.SUCCESS_MS.
CONFETTI_MS = 2400
CONFETTI_FADE_MS = 700
CONFETTI_COUNT = 36
CONFETTI_RGB = (
    (255, 176, 0),
    (255, 99, 99),
    (90, 200, 250),
    (120, 220, 120),
    (200, 140, 255),
    (255, 240, 120),
)


def retry_reason_text(reason):
    return REASON_TEXT.get(reason, REASON_DEFAULT)


def goal_reached(previous_total, result_total):
    """True when a sync takes the confirmed total to the goal from below."""
    if result_total is None or result_total < layout.GOAL:
        return False
    return previous_total is None or previous_total < layout.GOAL


def _held_total(confirmed, pending):
    """(total_text, plus_text, subtitle, unshared) for a not-yet-synced view.

    A first-use badge has no team total: its own steps show in amber and the
    caption says so instead of fabricating one.
    """
    if confirmed is None:
        return layout.format_count(pending), None, layout.FIRST_USE_CAPTION, True
    plus = "+" + layout.format_count(pending) if pending > 0 else None
    return layout.format_count(confirmed), plus, TOTAL_CAPTION, False


def view_model(session, warning=None):
    """What to draw for this session's state.

    Keys: state, title, total_text, plus_text (amber unshared +N or None),
    subtitle, hint (active states), reason (retry only), celebrate (confetti),
    goal_reached, show_total_is_new (the total is the freshly confirmed one),
    unshared_total (the big number is own unshared steps: amber), check.
    """
    state = session.state
    vm = {
        "state": state,
        "title": None,
        "total_text": None,
        "plus_text": None,
        "subtitle": None,
        "hint": None,
        "reason": None,
        "celebrate": False,
        "goal_reached": False,
        "show_total_is_new": False,
        "unshared_total": False,
        "check": False,
    }

    if state == sync.WALKING:
        main = layout.view_model(session.ledger, warning)
        vm["title"] = main["status_text"]
        vm["total_text"] = main["big_text"]
        vm["plus_text"] = main["plus_text"]
        vm["subtitle"] = main["caption"]
        vm["unshared_total"] = main["unshared_big"]
        return vm

    if state == sync.SUCCESS or state == sync.SEPARATE:
        total = session.result_total
        if total is None:
            total = session.confirmed_total
        vm["show_total_is_new"] = True
        vm["total_text"] = layout.format_count(total)
        if state == sync.SUCCESS:
            reached = goal_reached(session.previous_total, total)
            vm["goal_reached"] = reached
            vm["celebrate"] = True
            vm["check"] = True
            vm["title"] = TITLE_GOAL if reached else TITLE_SYNCED
            if session.result_added > 0:
                vm["subtitle"] = "+" + layout.format_count(session.result_added) + " together"
            else:
                vm["subtitle"] = TOTAL_CAPTION
        else:
            vm["title"] = TITLE_SEPARATE
            vm["subtitle"] = TOTAL_CAPTION
            if session.pending > 0:
                vm["plus_text"] = "+" + layout.format_count(session.pending)
        return vm

    total, plus, subtitle, unshared = _held_total(session.confirmed_total, session.pending)
    vm["total_text"] = total
    vm["plus_text"] = plus
    vm["subtitle"] = subtitle
    vm["unshared_total"] = unshared
    vm["hint"] = HINTS.get(state)
    if state == sync.HOLD:
        vm["title"] = TITLE_HOLD
    elif state == sync.CONNECTING:
        vm["title"] = TITLE_CONNECTING
    elif state == sync.EXCHANGE:
        vm["title"] = TITLE_EXCHANGE
    elif state == sync.AWAITING_ACK:
        vm["title"] = TITLE_AWAITING_ACK
    elif state == sync.UP_TO_DATE:
        vm["title"] = TITLE_UP_TO_DATE
    elif state == sync.RETRY:
        vm["title"] = TITLE_RETRY
        vm["reason"] = retry_reason_text(session.retry_reason)
        if session.confirmed_total is not None:
            vm["subtitle"] = "Still " + layout.format_count(session.confirmed_total) + " shared steps"
    return vm


# --- confetti ------------------------------------------------------------------

def confetti_particles(width, count=CONFETTI_COUNT):
    """Deterministic particles: (x0, fall px/s, sway px, sway rad/s, phase, colour, w, h)."""
    seed = 7
    out = []
    for i in range(count):
        vals = []
        for _ in range(6):
            seed = (seed * 75 + 74) % 65537  # tiny LCG, stays within small ints
            vals.append(seed / 65537)
        out.append(
            (
                int(vals[0] * width),
                80 + int(vals[1] * 100),
                4 + int(vals[2] * 10),
                2.0 + vals[3] * 3.0,
                vals[4] * 6.28,
                i % len(CONFETTI_RGB),
                3 + int(vals[5] * 3),
                5 + int(vals[5] * 4),
            )
        )
    return out


def confetti_pose(particle, t_ms):
    """(x, y) of a particle t_ms after the celebration started. Falls from above the screen."""
    x0, speed, sway, rate, phase, _colour, _w, h = particle
    t = t_ms / 1000
    return int(x0 + sway * math.sin(t * rate + phase)), int(-h + speed * t)


def confetti_alpha(t_ms):
    """0.0-1.0 opacity: full, then fading to 0 at CONFETTI_MS. 0 once it has ended."""
    if t_ms < 0:
        return 0.0
    if t_ms >= CONFETTI_MS:
        return 0.0
    fade_start = CONFETTI_MS - CONFETTI_FADE_MS
    if t_ms <= fade_start:
        return 1.0
    return (CONFETTI_MS - t_ms) / CONFETTI_FADE_MS
