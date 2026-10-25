"""Sync flow screens for the walking game (320x240 HIRES).

``draw(session)`` draws the screen for the session's state: the main walking
screen while walking, the previous confirmed total with the amber +N during the
exchange and on retry, and on success a dimmed scene under confetti with a
check mark, the new total and the amount added, then a prompt to move apart.

Texts and the confetti maths live in sync_layout.py (pure, laptop-tested). The
celebration is timed from ``badge.ticks_delta`` and is bounded: the confetti
fades out well before ``sync.SUCCESS_MS`` and the state itself moves on to the
separate prompt and then back to walking once the badges disconnect.

Uses the runtime globals badge, screen, color, shape and rect.
"""

import layout
import main_screen as ms
import sync
import sync_layout

W = ms.W
H = ms.H
CX = ms.CX
MAX_W = W - 2 * ms.MARGIN

TITLE_H = 20  # title height limit in the header strip of the active screens
BIG_TITLE_H = 44  # title height limit on the full-screen cards
CARD_TOTAL_H = 56  # total height limit on the full-screen cards
CARD_SUB_H = 24
CARD_GAP = 6
CHECK_SIZE = 34
LINE_GAP = 6

DIM_ACTIVE = 0.25
DIM_SUCCESS = 0.55
DIM_SEPARATE = 0.45

CELEBRATE = color.rgb(255, 226, 120)
CHECK_BG = color.rgb(60, 190, 110)
HINT = color.rgb(200, 215, 240)

# Fonts tallest first, from the main screen's measured list.
FIT_FONTS = list(ms.COUNT_FONTS)
if ms.SMALL_FONT not in FIT_FONTS:
    FIT_FONTS.append(ms.SMALL_FONT)
CARD_TOTAL_FONTS = [f for f in FIT_FONTS if ms.FONT_HEIGHT[id(f)] <= CARD_TOTAL_H] or [ms.SMALL_FONT]

PARTICLES = sync_layout.confetti_particles(W)
CONFETTI_PENS = {}  # opacity byte -> list of pens, built lazily and reused

_last_state = None
_celebration_ms = 0


def _pick_font(text, max_w, max_h):
    for f in FIT_FONTS:
        if ms.FONT_HEIGHT[id(f)] <= max_h and ms.measure(text, f) <= max_w:
            return f
    return ms.SMALL_FONT


def _confetti_pens(alpha):
    key = int(layout.alpha_byte(alpha))
    pens = CONFETTI_PENS.get(key)
    if pens is None:
        pens = CONFETTI_PENS[key] = [color.rgb(r, g, b, key) for (r, g, b) in sync_layout.CONFETTI_RGB]
    return pens


def _draw_confetti(t_ms):
    alpha = sync_layout.confetti_alpha(t_ms)
    if alpha <= 0:
        return
    pens = _confetti_pens(alpha)
    for p in PARTICLES:
        x, y = sync_layout.confetti_pose(p, t_ms)
        if y > H:
            continue
        screen.pen = pens[p[5]]
        screen.rectangle(rect(x, y, p[6], p[7]))


def _draw_check(top):
    r = CHECK_SIZE // 2
    screen.pen = CHECK_BG
    screen.shape(shape.rounded_rectangle(CX - r, top, CHECK_SIZE, CHECK_SIZE, r))
    screen.pen = ms.WHITE
    x0, y0 = CX - 9, top + r
    x1, y1 = CX - 3, top + r + 7
    x2, y2 = CX + 10, top + r - 7
    for d in (-1, 0, 1):  # three offset strokes make a thick check mark
        screen.line(x0, y0 + d, x1, y1 + d)
        screen.line(x1, y1 + d, x2, y2 + d)


def _draw_total_pair(vm, fonts, y):
    f, total_x, plus_x, _ = layout.fit_pair(vm["total_text"], vm["plus_text"], fonts, ms.measure, MAX_W, CX)
    pen = ms.AMBER if vm["unshared_total"] else ms.WHITE
    ms.draw_text(vm["total_text"], total_x, y, pen, f)
    if plus_x is not None:
        ms.draw_text(vm["plus_text"], plus_x, y, ms.AMBER, f)
    return f


def _draw_card(vm):
    """Full-screen card: optional check mark, title, total, subtitle, centred as a stack."""
    title_f = _pick_font(vm["title"], MAX_W, BIG_TITLE_H)
    sub_f = _pick_font(vm["subtitle"], MAX_W, CARD_SUB_H)
    total_f = layout.fit_pair(vm["total_text"], vm["plus_text"], CARD_TOTAL_FONTS, ms.measure, MAX_W, CX)[0]
    title_h = ms.FONT_HEIGHT[id(title_f)]
    total_h = ms.FONT_HEIGHT[id(total_f)]
    sub_h = ms.FONT_HEIGHT[id(sub_f)]

    stack_h = title_h + CARD_GAP + total_h + CARD_GAP + sub_h
    if vm["check"]:
        stack_h += CHECK_SIZE + CARD_GAP
    y = max(4, (H - stack_h) // 2)

    if vm["check"]:
        _draw_check(y)
        y += CHECK_SIZE + CARD_GAP
    title_pen = CELEBRATE if vm["celebrate"] else ms.WHITE
    ms.draw_text(vm["title"], CX - ms.measure(vm["title"], title_f) // 2, y, title_pen, title_f)
    y += title_h + CARD_GAP
    _draw_total_pair(vm, CARD_TOTAL_FONTS, y)
    y += total_h + CARD_GAP
    ms.draw_text(vm["subtitle"], CX - ms.measure(vm["subtitle"], sub_f) // 2, y, ms.WHITE, sub_f)


def _draw_active(vm):
    """Main-screen layout: title strip, total band, subtitle and one detail line."""
    title_f = _pick_font(vm["title"], MAX_W, TITLE_H)
    ms.draw_text(vm["title"], CX - ms.measure(vm["title"], title_f) // 2, 2, ms.WHITE, title_f)

    f, total_x, plus_x, _ = layout.fit_pair(
        vm["total_text"], vm["plus_text"], ms.COUNT_FONTS, ms.measure, ms.MAX_PAIR_W, CX
    )
    y = ms.BAND_TOP + (ms.BAND_BOTTOM - ms.BAND_TOP - ms.FONT_HEIGHT[id(f)]) // 2
    ms.draw_text(vm["total_text"], total_x, y, ms.AMBER if vm["unshared_total"] else ms.WHITE, f)
    if plus_x is not None:
        ms.draw_text(vm["plus_text"], plus_x, y, ms.AMBER, f)

    ms.draw_text_centred(vm["subtitle"], ms.CAPTION_Y, ms.WHITE, ms.SMALL_FONT)
    line = vm["reason"] or vm["hint"]
    if line:
        pen = ms.WARN if vm["reason"] else HINT
        ms.draw_text_centred(line, ms.CAPTION_Y + ms.FONT_HEIGHT[id(ms.SMALL_FONT)] + LINE_GAP, pen, ms.SMALL_FONT)


def _advance_celebration(state):
    """Milliseconds since SUCCESS was entered, accumulated from badge.ticks_delta."""
    global _last_state, _celebration_ms
    if state != _last_state:
        _last_state = state
        _celebration_ms = 0
    if state == sync.SUCCESS:
        dt = badge.ticks_delta
        if dt > 100:  # a stall must not skip the whole animation
            dt = 100
        _celebration_ms += dt
    return _celebration_ms


def draw(session, warning=None):
    """Draw one frame for the session's current state.

    WALKING delegates to the main screen (warning is passed through). Every
    other state draws the matching sync screen; no screen before SUCCESS shows
    anything but the previous confirmed total.
    """
    state = session.state
    t = _advance_celebration(state)
    if state == sync.WALKING:
        ms.draw(session.ledger, warning)
        return

    vm = sync_layout.view_model(session)
    if state == sync.SUCCESS:
        ms.draw_scene(session.ledger, DIM_SUCCESS)
        _draw_confetti(t)
        _draw_card(vm)
    elif state == sync.SEPARATE:
        ms.draw_scene(session.ledger, DIM_SEPARATE)
        _draw_card(vm)
    else:
        ms.draw_scene(session.ledger, DIM_ACTIVE)
        _draw_active(vm)
