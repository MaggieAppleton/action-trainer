"""Desktop tooling for the Walk Together meadow screen.

    python tools/walk_screen_preview.py assets     # rebuild walk_together/assets/*.png
    python tools/walk_screen_preview.py captures   # render docs/walk_together/*.png

Needs Pillow (`pip install pillow`); it is not a runtime dependency.

The captures are DESKTOP MOCK renders, not photos of a badge. They run the real
`walk_together/screen.py` draw code against a Pillow-backed stand-in for the
badge's `screen`, `image`, `shape`, `color`, `font` and `badge` globals. The
stand-in font is Pillow's built-in one, so glyph widths differ from the badge's
`font.nope`; check text fit on hardware.
"""

import builtins
import importlib
import math
import os
import random
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
WALK_DIR = os.path.join(ROOT, "walk_together")
ASSET_DIR = os.path.join(WALK_DIR, "assets")
OUT_DIR = os.path.join(ROOT, "docs", "walk_together")

# --------------------------------------------------------------------------
# Assets: small paletted PNGs (index 0 is transparent where noted)
# --------------------------------------------------------------------------


def _palette_image(size, colours, transparent=None):
    img = Image.new("P", size, 0)
    flat = []
    for c in colours:
        flat.extend(c)
    img.putpalette(flat + [0] * (768 - len(flat)))
    if transparent is not None:
        img.info["transparency"] = transparent
    return img


def build_meadow():
    colours = [
        (96, 170, 235),  # 0 sky top
        (128, 194, 242),  # 1 sky mid
        (170, 220, 248),  # 2 sky low
        (255, 255, 255),  # 3 cloud
        (126, 176, 168),  # 4 far hill
        (90, 160, 100),  # 5 near hill
        (112, 192, 82),  # 6 meadow light
        (84, 160, 66),  # 7 meadow dark
        (250, 250, 240),  # 8 daisy
        (255, 214, 64),  # 9 buttercup
        (240, 120, 160),  # 10 clover
        (110, 76, 50),  # 11 trunk
        (50, 120, 60),  # 12 leaf
        (36, 92, 50),  # 13 leaf dark
        (255, 236, 130),  # 14 sun
    ]
    img = _palette_image((160, 120), colours)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 159, 19), fill=0)
    d.rectangle((0, 20, 159, 37), fill=1)
    d.rectangle((0, 38, 159, 59), fill=2)
    d.ellipse((130, 12, 142, 24), fill=14)
    for cx, cy in ((24, 14), (88, 24), (118, 10)):
        d.ellipse((cx, cy, cx + 20, cy + 6), fill=3)
        d.ellipse((cx + 5, cy - 3, cx + 15, cy + 3), fill=3)
    for cx, r in ((20, 26), (72, 34), (128, 30)):
        d.ellipse((cx - r, 52, cx + r, 52 + 2 * r), fill=4)
    for cx, r in ((0, 30), (58, 24), (110, 34), (160, 26)):
        d.ellipse((cx - r, 60, cx + r, 60 + 2 * r), fill=5)
    d.rectangle((0, 66, 159, 119), fill=6)
    rng = random.Random(7)
    for _ in range(150):
        x, y = rng.randrange(160), rng.randrange(68, 120)
        d.line((x, y, x + rng.randrange(2, 5), y), fill=7)
    for _ in range(60):
        x, y = rng.randrange(1, 159), rng.randrange(68, 118)
        d.point((x, y), fill=rng.choice((8, 9, 10)))
    for tx, ty in ((14, 52), (150, 54), (96, 58)):
        d.rectangle((tx, ty + 6, tx + 1, ty + 11), fill=11)
        d.ellipse((tx - 4, ty - 4, tx + 6, ty + 8), fill=12)
        d.ellipse((tx - 1, ty - 2, tx + 4, ty + 3), fill=13)
    return img


def _walker(img, ox, shirt, skin, legs, frame, y0=0):
    px = img.putpixel
    for x, y in ((1, 0), (2, 0), (1, 1), (2, 1)):
        px((ox + x, y0 + y), skin)
    for x, y in ((1, 2), (2, 2), (1, 3), (2, 3), (1, 4), (2, 4), (0, 2), (3, 2), (0, 3), (3, 3)):
        px((ox + x, y0 + y), shirt)
    if frame == 0:
        cells = ((1, 5), (1, 6), (1, 7), (2, 5), (2, 6), (2, 7))
    else:
        cells = ((1, 5), (1, 6), (0, 7), (2, 5), (2, 6), (3, 7))
    for x, y in cells:
        px((ox + x, y0 + y), legs)


def build_marker():
    colours = [
        (0, 0, 0),  # 0 transparent
        (60, 110, 230),  # 1 blue shirt
        (240, 140, 50),  # 2 orange shirt
        (250, 214, 170),  # 3 skin
        (50, 50, 70),  # 4 legs
        (150, 150, 160),  # 5 grey shirt A
        (115, 115, 125),  # 6 grey shirt B
        (195, 195, 200),  # 7 grey skin
        (80, 80, 90),  # 8 grey legs
    ]
    img = _palette_image((16, 16), colours, transparent=0)
    for frame in (0, 1):
        _walker(img, frame * 8, 1, 3, 4, frame, 0)
        _walker(img, frame * 8 + 4, 2, 3, 4, frame, 0)
        _walker(img, frame * 8, 5, 7, 8, frame, 8)
        _walker(img, frame * 8 + 4, 6, 7, 8, frame, 8)
    return img


def build_flag():
    colours = [
        (0, 0, 0),  # 0 transparent
        (90, 60, 40),  # 1 pole
        (250, 250, 250),  # 2 white pennant
        (170, 175, 190),  # 3 shade
        (255, 205, 70),  # 4 gold pennant
        (200, 140, 20),  # 5 gold shade
    ]
    img = _palette_image((16, 10), colours, transparent=0)
    for col, (main, shade) in enumerate(((2, 3), (4, 5))):
        ox = col * 8
        for y in range(10):
            img.putpixel((ox + 1, y), 1)
        for row, width in enumerate((5, 4, 3, 2)):
            for x in range(width):
                img.putpixel((ox + 2 + x, row), main)
            img.putpixel((ox + 2, row), shade)
    return img


def build_assets():
    os.makedirs(ASSET_DIR, exist_ok=True)
    for name, img in (("meadow", build_meadow()), ("marker", build_marker()), ("flag", build_flag())):
        path = os.path.join(ASSET_DIR, name + ".png")
        img.save(path, optimize=True)
        print("wrote", os.path.relpath(path, ROOT), os.path.getsize(path), "bytes")


# --------------------------------------------------------------------------
# Pillow-backed stand-ins for the badge runtime globals
# --------------------------------------------------------------------------


class _Sheet:
    def __init__(self, img, cols, rows):
        self.img, self.cols, self.rows = img, cols, rows

    def sprite(self, col, row):
        w, h = self.img.width // self.cols, self.img.height // self.rows
        return self.img.crop((col * w, row * h, (col + 1) * w, (row + 1) * h))


class _ImageNs:
    OFF, X2, X4, CENTER = 0, 2, 4, 1

    @staticmethod
    def load(path):
        img = Image.open(os.path.join(WALK_DIR, path)).convert("RGBA")
        img.spritesheet = lambda cols, rows: _Sheet(img, cols, rows)
        return img


class _FontNs:
    def __getattr__(self, name):
        return name


class _Color:
    @staticmethod
    def rgb(r, g, b, a=255):
        return (r, g, b, a)


class _Shape:
    @staticmethod
    def rectangle(x, y, w, h):
        return ("rect", x, y, w, h, 0)

    @staticmethod
    def rounded_rectangle(x, y, w, h, r=0, *_):
        return ("rect", x, y, w, h, r)

    @staticmethod
    def circle(x, y, r):
        return ("circle", x, y, r)

    @staticmethod
    def star(x, y, points, inner, outer):
        pts = []
        for i in range(points * 2):
            r = outer if i % 2 == 0 else inner
            a = -math.pi / 2 + i * math.pi / points
            pts.append((x + r * math.cos(a), y + r * math.sin(a)))
        return ("poly", pts)


class _Badge:
    def __init__(self):
        self.ticks = 0
        self.ticks_delta = 16

    def upside_down(self):
        return False


class PilScreen:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.canvas = Image.new("RGBA", (width, height), (0, 0, 0, 255))
        self.pen = (255, 255, 255, 255)
        self.font = None
        self._fonts = {}

    def _layer_draw(self, fn):
        layer = Image.new("RGBA", self.canvas.size, (0, 0, 0, 0))
        fn(ImageDraw.Draw(layer), self.pen)
        self.canvas.alpha_composite(layer)

    def rectangle(self, x, y, w, h):
        self._layer_draw(lambda d, p: d.rectangle((x, y, x + w - 1, y + h - 1), fill=p))

    def shape(self, s):
        if s[0] == "rect":
            _, x, y, w, h, r = s
            self._layer_draw(lambda d, p: d.rounded_rectangle((x, y, x + w - 1, y + h - 1), radius=r, fill=p))
        elif s[0] == "circle":
            _, x, y, r = s
            self._layer_draw(lambda d, p: d.ellipse((x - r, y - r, x + r, y + r), fill=p))
        else:
            self._layer_draw(lambda d, p: d.polygon(s[1], fill=p))

    def line(self, x0, y0, x1, y1):
        self._layer_draw(lambda d, p: d.line((x0, y0, x1, y1), fill=p, width=1))

    def _pil_font(self, size):
        px = max(6, int(round(8 * size)))
        if px not in self._fonts:
            self._fonts[px] = ImageFont.load_default(size=px)
        return self._fonts[px]

    def measure_text(self, text, font_size=1):
        f = self._pil_font(font_size)
        l, t, r, b = f.getbbox(text)
        return (r - l, max(b, int(round(8 * font_size))))

    def text(self, text, x, y, size=1):
        f = self._pil_font(size)
        self._layer_draw(lambda d, p: d.text((x, y), text, font=f, fill=p))

    def blit(self, img, dest):
        if isinstance(dest, tuple) and dest[0] == "vec2":
            self.canvas.alpha_composite(img, (int(round(dest[1])), int(round(dest[2]))))
            return
        _, x, y, w, h = dest
        scaled = img.resize((max(1, int(round(w))), max(1, int(round(h)))), Image.NEAREST)
        self.canvas.alpha_composite(scaled, (int(round(x)), int(round(y))))


def _vec2(x, y):
    return ("vec2", x, y)


def _rect(x, y, w, h):
    return ("rect", x, y, w, h)


GLOBAL_NAMES = ("screen", "badge", "image", "font", "color", "shape", "vec2", "rect")


def install_runtime(width, height):
    screen, badge = PilScreen(width, height), _Badge()
    builtins.screen, builtins.badge = screen, badge
    builtins.image, builtins.font = _ImageNs(), _FontNs()
    builtins.color, builtins.shape = _Color, _Shape()
    builtins.vec2, builtins.rect = _vec2, _rect
    return screen, badge


def uninstall_runtime():
    for name in GLOBAL_NAMES:
        if hasattr(builtins, name):
            delattr(builtins, name)


# --------------------------------------------------------------------------
# Captures
# --------------------------------------------------------------------------


def _make_ledger():
    import ledger

    led = ledger.Ledger()
    led.add_steps(700)
    led.pair(0xB2)
    led.receive(0xB2, 500, 1_000)  # last shared pooled total: 1200
    return led


def _frames(screen_mod, badge, model, count=12, dt=100):
    for _ in range(count):
        badge.ticks_delta = dt
        badge.ticks += dt
        screen_mod.draw(model)


def render_states(width, height):
    """Return {state name: PIL image} for one display size."""
    sys.path.insert(0, WALK_DIR)
    screen, badge = install_runtime(width, height)
    try:
        sys.modules.pop("screen", None)
        meadow = importlib.import_module("screen")
        out = {}

        led = _make_ledger()
        led.add_steps(750)  # pooled 1950, partner's 500 shared moments ago
        led.receive(0xB2, 500, 3_000)
        model = meadow.build_view_model(led, True, 6_000)
        meadow.reset()
        _frames(meadow, badge, model)
        out["in-range"] = screen.canvas.copy()

        screen.canvas.paste((0, 0, 0, 255), (0, 0, width, height))
        led = _make_ledger()
        led.add_steps(300)  # walked 300 apart; last share was 3 minutes ago
        model = meadow.build_view_model(led, False, 181_000)
        meadow.reset()
        _frames(meadow, badge, model)
        out["out-of-range"] = screen.canvas.copy()

        screen.canvas.paste((0, 0, 0, 255), (0, 0, width, height))
        led = _make_ledger()
        led.add_steps(1290)  # pooled 2490, just short of "Old oak" at 2500
        meadow.reset()
        _frames(meadow, badge, meadow.build_view_model(led, True, 4_000), count=5)
        led.add_steps(30)  # crosses "Old oak" at 2500
        _frames(meadow, badge, meadow.build_view_model(led, True, 5_000), count=6)
        out["goal-reached"] = screen.canvas.copy()
        return out
    finally:
        sys.modules.pop("screen", None)
        uninstall_runtime()
        sys.path.remove(WALK_DIR)


def build_captures():
    os.makedirs(OUT_DIR, exist_ok=True)
    for (w, h), name, zoom in (((320, 240), "hires-320x240", 1), ((160, 120), "lowres-160x120-x3", 3)):
        for state, img in render_states(w, h).items():
            if zoom != 1:
                img = img.resize((w * zoom, h * zoom), Image.NEAREST)
            path = os.path.join(OUT_DIR, "%s-%s.png" % (state, name))
            img.convert("RGB").save(path, optimize=True)
            print("wrote", os.path.relpath(path, ROOT))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "assets":
        build_assets()
    elif cmd == "captures":
        build_captures()
    else:
        sys.exit(__doc__)
