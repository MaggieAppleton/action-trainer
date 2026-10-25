"""Count + landscape main screen for the walking game (320x240 HIRES).

A large centred team total sits above two hikers walking a coastal trail
toward a lighthouse. The amber +N (unshared steps) shares the total's size and
baseline and the pair is fitted together. The partner hiker is drawn faded and
the lighthouse is lit only by a confirmed total at or past the goal.

Uses the runtime globals badge, screen, font, color, shape, rect and the
HIRES/VSYNC constants (docs/badge/AGENTS.md). Everything reusable (fonts,
colours, static rectangles) is built once at module scope. Layout and text
decisions live in layout.py so they can be tested on a laptop.
"""

import math

import layout

badge.mode(HIRES | VSYNC)

W = screen.width
H = screen.height
CX = W // 2

# Vertical layout: fixed status line, count band, fixed caption, then scenery.
STATUS_Y = 5
BAND_TOP = 24
BAND_BOTTOM = 98
CAPTION_Y = 102
MARGIN = 12
MAX_PAIR_W = W - 2 * MARGIN

HORIZON_Y = 168
GROUND_Y = 200
TRAIL_Y = 212
FOOT_Y = 226
LIGHT_X = 270
TOWER_H = 60
TOWER_TOP = GROUND_Y - TOWER_H
TRAIL_X0 = 40
TRAIL_X1 = LIGHT_X - 26
PARTNER_GAP = 28


# --- colours -----------------------------------------------------------------

def _rgb(r, g, b, a=255):
    return color.rgb(r, g, b, a)


WHITE = _rgb(255, 255, 255)
SHADOW = _rgb(10, 16, 36)
AMBER = _rgb(255, 176, 0)
WARN = _rgb(255, 150, 100)
SEA_DEEP = _rgb(22, 60, 120)
SEA_LIGHT = _rgb(44, 96, 160)
WAVE = _rgb(150, 190, 235)
GRASS = _rgb(58, 120, 70)
GRASS_DARK = _rgb(40, 92, 56)
CLIFF = _rgb(96, 84, 74)
TRAIL = _rgb(214, 184, 130)
TOWER_WHITE = _rgb(240, 240, 244)
TOWER_RED = _rgb(200, 56, 52)
LANTERN_OFF = _rgb(58, 62, 84)
LANTERN_ON = _rgb(255, 222, 110)
ROOF = _rgb(60, 60, 72)
GLOW = _rgb(255, 222, 110, 70)

PARTNER_A = layout.alpha_byte(layout.PARTNER_ALPHA)


def _hiker_palette(alpha):
    return {
        "skin": _rgb(240, 200, 160, alpha),
        "body": _rgb(235, 110, 70, alpha),
        "pack": _rgb(120, 70, 50, alpha),
        "legs": _rgb(50, 60, 90, alpha),
    }


ME_PALETTE = _hiker_palette(255)
PARTNER_PALETTE = _hiker_palette(PARTNER_A)


# --- static scenery built once -----------------------------------------------

def _sky_bands():
    bands = []
    n = 28
    top = (18, 32, 78)
    bottom = (126, 156, 210)
    step = HORIZON_Y // n + 1
    for i in range(n):
        t = i / (n - 1)
        c = _rgb(
            int(top[0] + (bottom[0] - top[0]) * t),
            int(top[1] + (bottom[1] - top[1]) * t),
            int(top[2] + (bottom[2] - top[2]) * t),
        )
        bands.append((c, rect(0, i * step, W, step + 1)))
    return bands


SKY = _sky_bands()
SEA_RECT = rect(0, HORIZON_Y, W, GROUND_Y - HORIZON_Y)
SEA_SHINE_RECT = rect(0, HORIZON_Y, W, 8)
GRASS_RECT = rect(0, GROUND_Y + 4, W, H - GROUND_Y - 4)
GRASS_EDGE_RECT = rect(0, GROUND_Y + 4, W, 6)
CLIFF_RECT = rect(0, GROUND_Y, W, 4)
TRAIL_SHAPE = shape.rounded_rectangle(10, TRAIL_Y, W - 20, 18, 8)


def _build_fonts():
    """Fonts ordered tallest first, using only the documented font names."""
    sized = []
    for f in (font.nope, font.sins, font.ark, font.ziplock):
        screen.font = f
        sized.append((screen.measure_text("0")[1], f))
    sized.sort(key=lambda item: item[0], reverse=True)
    band_h = BAND_BOTTOM - BAND_TOP
    big = [f for (h, f) in sized if h <= band_h]
    if not big:
        big = [sized[-1][1]]
    return big, sized[-1][1], dict((id(f), h) for (h, f) in sized)


COUNT_FONTS, SMALL_FONT, FONT_HEIGHT = _build_fonts()

_clock_ms = 0


# --- text helpers --------------------------------------------------------------

def _measure(text, f):
    screen.font = f
    return screen.measure_text(text)[0]


def _text(text, x, y, pen, f, shadow=True):
    screen.font = f
    if shadow:
        screen.pen = SHADOW
        screen.text(text, x + 1, y + 1)
    screen.pen = pen
    screen.text(text, x, y)


def _text_centred(text, y, pen, f):
    _text(text, CX - _measure(text, f) // 2, y, pen, f)


# --- scenery drawing -----------------------------------------------------------

def _draw_sky_and_sea(t):
    for (c, r) in SKY:
        screen.pen = c
        screen.rectangle(r)
    screen.pen = SEA_DEEP
    screen.rectangle(SEA_RECT)
    screen.pen = SEA_LIGHT
    screen.rectangle(SEA_SHINE_RECT)
    screen.pen = WAVE
    for i in range(6):
        x = int((i * 61 + t * 0.012) % (W + 20)) - 10
        y = HORIZON_Y + 10 + (i % 3) * 9
        screen.line(x, y, x + 14, y)
    screen.pen = CLIFF
    screen.rectangle(CLIFF_RECT)
    screen.pen = GRASS
    screen.rectangle(GRASS_RECT)
    screen.pen = GRASS_DARK
    screen.rectangle(GRASS_EDGE_RECT)
    screen.pen = TRAIL
    screen.shape(TRAIL_SHAPE)


def _draw_lighthouse(lit, t):
    if lit:
        pulse = 0.75 + 0.25 * math.sin(t / 400)
        screen.pen = _rgb(255, 232, 150, int(60 * pulse))
        screen.rectangle(rect(0, TOWER_TOP - 22, LIGHT_X - 8, 8))
        screen.pen = GLOW
        screen.shape(shape.rounded_rectangle(LIGHT_X - 18, TOWER_TOP - 34, 36, 32, 14))
    stripe_h = TOWER_H // 5
    for i in range(5):
        w = 26 - i * 2
        screen.pen = TOWER_RED if i % 2 == 0 else TOWER_WHITE
        screen.rectangle(rect(LIGHT_X - w // 2, TOWER_TOP + i * stripe_h, w, stripe_h))
    screen.pen = ROOF
    screen.rectangle(rect(LIGHT_X - 13, TOWER_TOP - 4, 26, 4))
    screen.pen = LANTERN_ON if lit else LANTERN_OFF
    screen.rectangle(rect(LIGHT_X - 6, TOWER_TOP - 16, 12, 12))
    screen.pen = ROOF
    screen.rectangle(rect(LIGHT_X - 9, TOWER_TOP - 20, 18, 4))
    screen.rectangle(rect(LIGHT_X - 2, TOWER_TOP - 25, 4, 5))
    screen.pen = CLIFF
    screen.shape(shape.rounded_rectangle(LIGHT_X - 20, GROUND_Y - 4, 40, 10, 4))


def _draw_hiker(x, phase, palette):
    swing = int(math.sin(phase) * 4)
    bob = -int(abs(math.sin(phase)) * 2)
    x = int(x)
    screen.pen = palette["legs"]
    screen.shape(shape.rounded_rectangle(x - 4 + swing, FOOT_Y - 10, 3, 10, 1))
    screen.shape(shape.rounded_rectangle(x + 1 - swing, FOOT_Y - 10, 3, 10, 1))
    screen.pen = palette["pack"]
    screen.shape(shape.rounded_rectangle(x - 9, FOOT_Y - 22 + bob, 5, 10, 2))
    screen.pen = palette["body"]
    screen.shape(shape.rounded_rectangle(x - 5, FOOT_Y - 24 + bob, 10, 15, 3))
    screen.pen = palette["skin"]
    screen.shape(shape.rounded_rectangle(x - 4, FOOT_Y - 33 + bob, 8, 8, 4))


def _draw_hikers(vm, t):
    walk = t / 1000 * 2 * math.pi * 1.6  # about 1.6 strides per second
    me_x = TRAIL_X0 + vm["progress"] * (TRAIL_X1 - TRAIL_X0)
    if vm["show_partner"]:
        _draw_hiker(max(14, me_x - PARTNER_GAP), walk + 1.2, PARTNER_PALETTE)
    _draw_hiker(me_x, walk, ME_PALETTE)


# --- public API ----------------------------------------------------------------

def draw(ledger, warning=None):
    """Draw one frame of the main screen for this ledger.

    warning is None or one of layout.WARN_*; it replaces the status line text
    with a warning while the saved total and +N stay on screen.
    """
    global _clock_ms
    dt = badge.ticks_delta
    if dt > 100:  # a stall or first frame must not make the hikers jump
        dt = 100
    _clock_ms += dt

    vm = layout.view_model(ledger, warning)
    _draw_sky_and_sea(_clock_ms)
    _draw_lighthouse(vm["lighthouse_lit"], _clock_ms)
    _draw_hikers(vm, _clock_ms)

    _text_centred(vm["status_text"], STATUS_Y, WARN if vm["warning"] else WHITE, SMALL_FONT)

    f, total_x, plus_x, _ = layout.fit_pair(
        vm["big_text"], vm["plus_text"], COUNT_FONTS, _measure, MAX_PAIR_W, CX
    )
    y = BAND_TOP + (BAND_BOTTOM - BAND_TOP - FONT_HEIGHT[id(f)]) // 2
    _text(vm["big_text"], total_x, y, AMBER if vm["unshared_big"] else WHITE, f)
    if plus_x is not None:
        _text(vm["plus_text"], plus_x, y, AMBER, f)

    _text_centred(vm["caption"], CAPTION_Y, WHITE, SMALL_FONT)
