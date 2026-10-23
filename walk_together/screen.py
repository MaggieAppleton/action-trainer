"""Meadow walking screen for Walk Together.

Plain MicroPython. Uses the badge runtime globals (`screen`, `badge`, `image`,
`font`, `color`, `shape`, `vec2`, `rect`) and nothing else, so the same code
draws on the badge and on the desktop test fakes.

Import it under another name in the app (`import screen as meadow`): a plain
`import screen` would shadow the runtime `screen` global inside the app.

Everything is laid out on a 160x120 design grid and scaled by
`screen.width / 160`, so it works in the default 160x120 mode and in HIRES
(320x240). The firmware keeps the display upright when the badge is inverted,
so nothing here depends on orientation.

The screen is driven by one plain dict (see `build_view_model`):

    pooled_total        own + partner's highest known total
    last_shared_total   pooled total at the last exchange
    own_new_steps       own steps counted since the last exchange
    in_range            True while partner packets are arriving
    seconds_since_share seconds since the last exchange, or None
    goal                name of the next goal, or None when all are reached
    steps_to_next       pooled steps left to the next goal
    progress            0..1 within the current leg (ledger goal_info())
    goal_index          goals reached so far
    goal_count          goals along the walk
    last_goal           name of the most recently reached goal, or None
"""

import math

# --- Provisional layout: the plan has not decided the step count's size or
# --- position. Change these constants to adjust it.
COUNT_SIZE = 2  # step count text size, in multiples of the status text size
COUNT_TOP = 3  # design px from the top edge to the count plate
STATUS_TEXT_SIZE = 1

DESIGN_W = 160
MARGIN = 4
PAD = 3

# Walk path across the meadow, in design px (x must increase).
PATH = ((12, 86), (44, 76), (80, 82), (114, 70), (148, 74))
MARKER_PX = 8
FLAG_W, FLAG_H = 8, 10

EASE_TAU_S = 0.35  # marker catches up to the ledger with this time constant
MOVING_EPS = 0.002
STEP_MS = 220  # walk animation frame length
BANNER_MS = 3000

WHITE = color.rgb(255, 255, 255)
PLATE = color.rgb(12, 22, 34, 175)
GOLD = color.rgb(255, 205, 70)
STAR = color.rgb(255, 235, 120)
DARK = color.rgb(30, 24, 10)
GREEN = color.rgb(60, 200, 90)
AMBER = color.rgb(255, 170, 50)
TINT = color.rgb(30, 40, 70, 90)
PATH_TODO = color.rgb(214, 186, 132)
PATH_DONE = color.rgb(255, 240, 170)

# Loaded once at import; never per frame.
MEADOW = image.load("assets/meadow.png")
MARKER = image.load("assets/marker.png").spritesheet(2, 2)
FLAGS = image.load("assets/flag.png").spritesheet(2, 1)
UI_FONT = font.nope


def format_ago(seconds):
    if seconds is None:
        return "NO SHARE YET"
    if seconds < 60:
        return "%dS AGO" % seconds
    if seconds < 3600:
        return "%dM AGO" % (seconds // 60)
    return "%dH AGO" % (seconds // 3600)


def build_view_model(ledger, in_range, now_ms):
    """Plain dict for `draw`, built from a ledger and the link's range state."""
    goal = ledger.goal_info()
    apart = ledger.apart_view()
    last = apart["last_exchange"]
    since = None if last is None else max(0, now_ms - last) // 1000
    index = goal["index"]
    return {
        "pooled_total": ledger.pooled_total(),
        "last_shared_total": apart["last_shared_total"],
        "own_new_steps": apart["own_new_steps"],
        "in_range": in_range,
        "seconds_since_share": since,
        "goal": goal["goal"],
        "steps_to_next": goal["steps_to_next"],
        "progress": goal["progress"],
        "goal_index": index,
        "goal_count": len(ledger.goals),
        "last_goal": ledger.goals[index - 1][0] if index > 0 else None,
    }


def path_point(fraction):
    """Design-px (x, y) a fraction 0..1 of the way along PATH."""
    if fraction <= 0:
        return PATH[0]
    x = PATH[0][0] + fraction * (PATH[-1][0] - PATH[0][0])
    for i in range(1, len(PATH)):
        x0, y0 = PATH[i - 1]
        x1, y1 = PATH[i]
        if x <= x1:
            return (x, y0 + (y1 - y0) * (x - x0) / (x1 - x0))
    return PATH[-1]


def _fit(text, max_width, size):
    while text and screen.measure_text(text, font_size=size)[0] > max_width:
        text = text[:-1]
    return text


class Meadow:
    def __init__(self):
        self.reset()

    def reset(self):
        self.shown = None  # eased walk fraction currently drawn
        self.anim_ms = 0
        self.seen_index = None
        self.banner_ms = 0
        self.banner_text = ""

    def draw(self, model):
        dt = badge.ticks_delta
        self.anim_ms += dt
        gs = screen.width / DESIGN_W  # geometry scale
        ts = max(1, screen.width // DESIGN_W)  # text size scale
        in_range = model["in_range"]
        count = model["goal_count"]
        index = model["goal_index"]

        target = (index + model["progress"]) / count if count else 0.0
        target = max(0.0, min(1.0, target))
        if self.shown is None:
            self.shown = target
        else:
            self.shown += (target - self.shown) * (1 - math.exp(-dt / 1000 / EASE_TAU_S))
        moving = abs(target - self.shown) > MOVING_EPS

        self.banner_ms = max(0, self.banner_ms - dt)
        if self.seen_index is not None and index > self.seen_index and model["last_goal"]:
            self.banner_ms = BANNER_MS
            self.banner_text = "REACHED " + model["last_goal"].upper() + "!"
        self.seen_index = index

        screen.font = UI_FONT
        screen.blit(MEADOW, rect(0, 0, screen.width, screen.height))
        if not in_range:
            screen.pen = TINT
            screen.rectangle(0, 0, screen.width, screen.height)

        mx, my = path_point(self.shown)
        self._draw_path(gs, mx)
        for i in range(count):
            fx, fy = path_point((i + 1) / count)
            screen.blit(
                FLAGS.sprite(1 if i < index else 0, 0),
                rect((fx - 1) * gs, (fy - FLAG_H) * gs, FLAG_W * gs, FLAG_H * gs),
            )
        self._draw_marker(gs, mx, my, in_range, moving)

        plate_bottom = self._draw_count(gs, ts, model)
        if model["goal"] is None:
            self._draw_banner(gs, ts, "ALL GOALS REACHED!", plate_bottom)
        elif self.banner_ms > 0:
            self._draw_banner(gs, ts, self.banner_text, plate_bottom)
        self._draw_status(gs, ts, model)

    def _draw_path(self, gs, marker_x):
        for i in range(1, len(PATH)):
            x0, y0 = PATH[i - 1]
            x1, y1 = PATH[i]
            if x0 >= marker_x:
                self._seg(gs, x0, y0, x1, y1, PATH_TODO)
            elif x1 <= marker_x:
                self._seg(gs, x0, y0, x1, y1, PATH_DONE)
            else:
                ym = y0 + (y1 - y0) * (marker_x - x0) / (x1 - x0)
                self._seg(gs, x0, y0, marker_x, ym, PATH_DONE)
                self._seg(gs, marker_x, ym, x1, y1, PATH_TODO)

    def _seg(self, gs, x0, y0, x1, y1, pen):
        screen.pen = pen
        screen.line(x0 * gs, y0 * gs, x1 * gs, y1 * gs)
        screen.line(x0 * gs, (y0 + 1) * gs, x1 * gs, (y1 + 1) * gs)

    def _draw_marker(self, gs, mx, my, in_range, moving):
        step = (self.anim_ms // STEP_MS) % 2 if moving else 0
        hop = 1 if step else 0
        screen.blit(
            MARKER.sprite(step, 0 if in_range else 1),
            rect((mx - MARKER_PX / 2) * gs, (my - MARKER_PX - hop) * gs, MARKER_PX * gs, MARKER_PX * gs),
        )

    def _draw_count(self, gs, ts, model):
        """Step count plate, top centre. Returns the plate's bottom edge in px."""
        in_range = model["in_range"]
        total = model["pooled_total"] if in_range else model["last_shared_total"]
        text = str(total)
        extra = "" if in_range or model["own_new_steps"] <= 0 else "+" + str(model["own_new_steps"])
        small = STATUS_TEXT_SIZE * ts
        pad = PAD * gs
        limit = screen.width - 2 * MARGIN * gs - 2 * pad
        big = COUNT_SIZE * ts
        gap = 3 * gs if extra else 0
        while big > small:
            w = screen.measure_text(text, font_size=big)[0]
            if extra:
                w += gap + screen.measure_text(extra, font_size=small)[0]
            if w <= limit:
                break
            big -= ts
        cw, ch = screen.measure_text(text, font_size=big)
        ew = screen.measure_text(extra, font_size=small)[0] if extra else 0
        eh = screen.measure_text(extra or "0", font_size=small)[1]

        line2 = ""
        if model["goal"] is not None:
            prefix, steps = "NEXT ", " " + str(model["steps_to_next"])
            room = limit - screen.measure_text(prefix + steps, font_size=small)[0]
            line2 = prefix + _fit(model["goal"].upper(), room, small) + steps
        l2w, l2h = screen.measure_text(line2 or "0", font_size=small)

        width = max(cw + gap + ew, l2w if line2 else 0) + 2 * pad
        height = ch + (l2h + gs if line2 else 0) + 2 * pad
        x = (screen.width - width) / 2
        y = COUNT_TOP * gs
        screen.pen = PLATE
        screen.shape(shape.rounded_rectangle(x, y, width, height, 3 * gs))

        screen.pen = WHITE
        screen.text(text, x + pad, y + pad, big)
        if extra:
            screen.pen = AMBER
            screen.text(extra, x + pad + cw + gap, y + pad + ch - eh, small)
        if line2:
            screen.pen = WHITE
            screen.text(line2, x + (width - l2w) / 2, y + pad + ch + gs, small)
        return y + height

    def _draw_banner(self, gs, ts, text, top):
        small = STATUS_TEXT_SIZE * ts
        tw, th = screen.measure_text(text, font_size=small)
        pad = PAD * gs
        width, height = tw + 2 * pad, th + 2 * pad
        x = (screen.width - width) / 2
        y = top + 3 * gs
        screen.pen = GOLD
        screen.shape(shape.rounded_rectangle(x, y, width, height, 3 * gs))
        screen.pen = DARK
        screen.text(text, x + pad, y + pad, small)
        screen.pen = STAR
        r = height / 2
        screen.shape(shape.star(x - r, y + r, 5, r * 0.45, r))
        screen.shape(shape.star(x + width + r, y + r, 5, r * 0.45, r))

    def _draw_status(self, gs, ts, model):
        """Bottom strip: In range / Out of range, and time apart."""
        small = STATUS_TEXT_SIZE * ts
        in_range = model["in_range"]
        label = "IN RANGE" if in_range else "OUT OF RANGE"
        since = model["seconds_since_share"]
        apart = None
        if not in_range:
            apart = format_ago(since) if since is None else "APART " + format_ago(since)
        lw, lh = screen.measure_text(label, font_size=small)
        aw, ah = screen.measure_text(apart or "0", font_size=small)
        pad = PAD * gs
        dot = lh * 0.6
        rows = 2 if apart else 1
        height = rows * lh + (rows - 1) * gs + 2 * pad
        top = screen.height - height
        screen.pen = PLATE
        screen.rectangle(0, top, screen.width, height)

        pen = GREEN if in_range else AMBER
        screen.pen = pen
        screen.shape(shape.circle(MARGIN * gs + dot / 2, top + pad + lh / 2, dot / 2))
        screen.pen = WHITE
        screen.text(label, MARGIN * gs + dot + 2 * gs, top + pad, small)
        if apart:
            screen.pen = AMBER
            screen.text(apart, MARGIN * gs, top + pad + lh + gs, small)


_meadow = Meadow()


def reset():
    _meadow.reset()


def draw(model):
    """Draw one frame of the meadow scene from a view-model dict."""
    _meadow.draw(model)
