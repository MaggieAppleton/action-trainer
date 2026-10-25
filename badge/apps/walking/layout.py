"""Pure layout and formatting helpers for the walking main screen.

No badge globals, so the view model and the fitting maths can be unit tested
on the laptop. MicroPython-compatible: plain functions and dicts only.
"""

GOAL = 10000
PARTNER_ALPHA = 0.55  # last-known partner hiker is drawn faded
NEAR_GOAL = 0.9  # fraction of the goal that counts as "near"
PAIR_GAP = 10  # px between the total and the amber +N

WARN_SYNC_UNAVAILABLE = "sync_unavailable"
WARN_SENSOR_UNAVAILABLE = "sensor_unavailable"
WARN_NOT_SAVED = "not_saved"

WARNING_TEXT = {
    WARN_SYNC_UNAVAILABLE: "Sync unavailable",
    WARN_SENSOR_UNAVAILABLE: "Step sensor unavailable",
    WARN_NOT_SAVED: "Progress not saved",
}

FIRST_USE_CAPTION = "Your steps, not synced yet"


def format_count(n):
    """1000025 -> '1,000,025'."""
    s = str(int(n))
    neg = s.startswith("-")
    if neg:
        s = s[1:]
    parts = []
    while len(s) > 3:
        parts.insert(0, s[-3:])
        s = s[:-3]
    parts.insert(0, s)
    return ("-" if neg else "") + ",".join(parts)


def alpha_byte(alpha):
    """0.0-1.0 opacity -> 0-255 channel value."""
    return int(alpha * 255 + 0.5)


def goal_state(confirmed):
    """'none' (never synced), 'walking', 'near' or 'reached'.

    Only a confirmed total counts; unshared pending steps never do.
    """
    if confirmed is None:
        return "none"
    if confirmed >= GOAL:
        return "reached"
    if confirmed >= GOAL * NEAR_GOAL:
        return "near"
    return "walking"


def progress_fraction(confirmed):
    if confirmed is None or confirmed <= 0:
        return 0.0
    if confirmed >= GOAL:
        return 1.0
    return confirmed / GOAL


def _partner_name(pid):
    return pid[:1].upper() + pid[1:]


def view_model(ledger, warning=None):
    """Everything the renderer needs, derived from the ledger."""
    confirmed = ledger.confirmed_total
    pending = ledger.pending
    first_use = confirmed is None
    if first_use:
        big_text = format_count(pending)
        plus_text = None
        caption = FIRST_USE_CAPTION
    else:
        big_text = format_count(confirmed)
        plus_text = "+" + format_count(pending) if pending > 0 else None
        caption = "of " + format_count(GOAL) + " shared steps"

    if warning is not None:
        status_text = "! " + WARNING_TEXT.get(warning, str(warning))
    elif ledger.partner:
        status_text = "Walking with " + _partner_name(ledger.partner)
    else:
        status_text = "Walking"

    return {
        "big_text": big_text,
        "plus_text": plus_text,
        "caption": caption,
        "status_text": status_text,
        "warning": warning is not None,
        "first_use": first_use,
        "unshared_big": first_use,  # the big number is unshared steps: amber
        "goal_state": goal_state(confirmed),
        "lighthouse_lit": confirmed is not None and confirmed >= GOAL,
        "progress": progress_fraction(confirmed),
        "show_partner": ledger.partner is not None,
        "partner_alpha": PARTNER_ALPHA,
    }


def pair_width(total_text, plus_text, size, measure_fn):
    width = measure_fn(total_text, size)
    if plus_text:
        width += PAIR_GAP + measure_fn(plus_text, size)
    return width


def fit_pair(total_text, plus_text, sizes, measure_fn, max_width, centre_x):
    """Fit the total and its +N together at one shared size.

    sizes: candidate sizes, largest first (opaque values passed to measure_fn).
    measure_fn(text, size) -> width in px.
    Returns (size, total_x, plus_x, pair_w). plus_x is None without a +N. Both
    pieces use the same size and are drawn at the same y, so they share a
    baseline. The pair is centred as one unit. If nothing fits, the smallest
    size is used.
    """
    chosen = sizes[-1]
    for size in sizes:
        if pair_width(total_text, plus_text, size, measure_fn) <= max_width:
            chosen = size
            break
    pair_w = pair_width(total_text, plus_text, chosen, measure_fn)
    left = centre_x - pair_w // 2
    total_x = left
    plus_x = None
    if plus_text:
        plus_x = left + measure_fn(total_text, chosen) + PAIR_GAP
    return chosen, total_x, plus_x, pair_w
