"""Desktop tests for walk_together/screen.py.

The badge runtime provides `screen`, `badge`, `image`, `font`, `color`,
`shape`, `vec2` and `rect` as globals. They are installed here as recording
fakes in `builtins`, which is how the module sees them on the badge too.
"""

import builtins
import importlib
import os
import sys
import unittest

WALK_DIR = os.path.join(os.path.dirname(__file__), "..", "walk_together")
sys.path.insert(0, WALK_DIR)

import ledger  # noqa: E402

GLOBALS = ("screen", "badge", "image", "font", "color", "shape", "vec2", "rect")


class FakeSprite:
    def __init__(self, sheet, col, row):
        self.sheet, self.col, self.row = sheet, col, row

    def __eq__(self, other):
        return (self.sheet, self.col, self.row) == (other.sheet, other.col, other.row)


class FakeSheet:
    def __init__(self, name):
        self.name = name

    def sprite(self, col, row):
        return FakeSprite(self.name, col, row)


class FakeImage:
    def __init__(self, path):
        self.path = path
        self.name = os.path.splitext(os.path.basename(path))[0]
        self.width, self.height = 160, 120

    def spritesheet(self, cols, rows):
        return FakeSheet(self.name)


class FakeImageNs:
    OFF, X2, X4 = 0, 2, 4
    CENTER = 1

    def __init__(self):
        self.loads = []

    def load(self, path):
        self.loads.append(path)
        return FakeImage(path)


class FakeFontNs:
    def __init__(self):
        self.accesses = 0

    def __getattr__(self, name):
        self.accesses += 1
        return "font:" + name


class FakeColor:
    @staticmethod
    def rgb(r, g, b, a=255):
        return (r, g, b, a)


class FakeShape:
    def __getattr__(self, name):
        return lambda *args: (name,) + args


class FakeBadge:
    def __init__(self):
        self.ticks = 0
        self.ticks_delta = 16
        self.flipped = False

    def upside_down(self):
        return self.flipped


class FakeScreen:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.pen = None
        self.font = None
        self.antialias = None
        self.calls = []

    def _rec(self, op, *args):
        self.calls.append((op, self.pen, self.font) + args)

    def rectangle(self, *a):
        self._rec("rectangle", *a)

    def shape(self, s):
        self._rec("shape", s)

    def line(self, *a):
        self._rec("line", *a)

    def blit(self, img, dest):
        self._rec("blit", img, dest)

    def text(self, text, x, y, size=1):
        self._rec("text", text, x, y, size)

    def measure_text(self, text, font_size=1):
        return (len(text) * 6 * font_size, 8 * font_size)

    def clear(self):
        self._rec("clear")

    # --- helpers for assertions ---
    def texts(self):
        return [c[3] for c in self.calls if c[0] == "text"]

    def markers(self):
        return [c for c in self.calls if c[0] == "blit" and getattr(c[3], "sheet", "") == "marker"]

    def marker_centre_x(self):
        (m,) = self.markers()
        _, x, _, w, _ = m[4]
        return x + w / 2


def vec2(x, y):
    return ("vec2", x, y)


def rect(x, y, w, h):
    return ("rect", x, y, w, h)


def vm(**over):
    base = {
        "pooled_total": 1950,
        "last_shared_total": 1950,
        "own_new_steps": 0,
        "in_range": True,
        "seconds_since_share": 4,
        "goal": "Old oak",
        "steps_to_next": 550,
        "progress": 0.5,
        "goal_index": 1,
        "goal_count": 5,
        "last_goal": "Meadow gate",
    }
    base.update(over)
    return base


class ScreenTestCase(unittest.TestCase):
    size = (160, 120)

    def setUp(self):
        self.saved = {n: getattr(builtins, n, None) for n in GLOBALS}
        self.screen = FakeScreen(*self.size)
        self.badge = FakeBadge()
        self.images = FakeImageNs()
        self.fonts = FakeFontNs()
        builtins.screen = self.screen
        builtins.badge = self.badge
        builtins.image = self.images
        builtins.font = self.fonts
        builtins.color = FakeColor
        builtins.shape = FakeShape()
        builtins.vec2 = vec2
        builtins.rect = rect
        sys.modules.pop("screen", None)
        self.mod = importlib.import_module("screen")
        self.mod.reset()

    def tearDown(self):
        for n, v in self.saved.items():
            if v is None:
                if hasattr(builtins, n):
                    delattr(builtins, n)
            else:
                setattr(builtins, n, v)
        sys.modules.pop("screen", None)

    def frame(self, model, dt=16):
        self.badge.ticks += dt
        self.badge.ticks_delta = dt
        self.screen.calls = []
        self.mod.draw(model)

    def settle(self, model, frames=200, dt=50):
        for _ in range(frames):
            self.frame(model, dt)


class MarkerTests(ScreenTestCase):
    def marker_x_at(self, **over):
        self.mod.reset()
        self.settle(vm(**over), frames=60)
        return self.screen.marker_centre_x()

    def test_marker_moves_right_as_progress_grows(self):
        xs = [self.marker_x_at(goal_index=0, progress=p / 10) for p in range(11)]
        self.assertEqual(xs, sorted(xs))
        self.assertGreater(xs[-1] - xs[0], self.screen.width * 0.15)

    def test_marker_stays_inside_the_screen_at_both_ends(self):
        for p in (0.0, 1.0):
            x = self.marker_x_at(goal_index=0, progress=p)
            self.assertGreater(x, 0)
            self.assertLess(x, self.screen.width)

    def test_leg_progress_is_continuous_across_goals(self):
        end_of_leg = self.marker_x_at(goal_index=0, progress=1.0)
        start_of_next = self.marker_x_at(goal_index=1, progress=0.0)
        self.assertAlmostEqual(end_of_leg, start_of_next, delta=0.5)

    def test_finished_walk_puts_marker_at_the_far_end(self):
        done = self.marker_x_at(goal_index=5, progress=1.0, goal=None, steps_to_next=0)
        almost = self.marker_x_at(goal_index=4, progress=0.99)
        self.assertGreaterEqual(done, almost)

    def test_first_frame_snaps_without_sweeping_from_zero(self):
        self.frame(vm(goal_index=2, progress=0.5))
        snapped = self.screen.marker_centre_x()
        self.settle(vm(goal_index=2, progress=0.5))
        self.assertAlmostEqual(snapped, self.screen.marker_centre_x(), delta=0.5)

    def test_easing_depends_on_ticks_delta_not_frame_count(self):
        self.settle(vm(goal_index=0, progress=0.0), frames=3)
        start = self.screen.marker_centre_x()
        target = vm(goal_index=0, progress=1.0)

        self.frame(target, dt=16)
        one_short = self.screen.marker_centre_x() - start
        self.mod.reset()
        self.settle(vm(goal_index=0, progress=0.0), frames=3)
        self.frame(target, dt=400)
        one_long = self.screen.marker_centre_x() - start
        self.assertGreater(one_short, 0)
        self.assertGreater(one_long, one_short * 5)

    def test_same_elapsed_time_gives_same_position_at_any_frame_rate(self):
        target = vm(goal_index=0, progress=1.0)
        self.settle(vm(goal_index=0, progress=0.0), frames=3)
        for _ in range(4):
            self.frame(target, dt=50)
        coarse = self.screen.marker_centre_x()

        self.mod.reset()
        self.settle(vm(goal_index=0, progress=0.0), frames=3)
        for _ in range(20):
            self.frame(target, dt=10)
        fine = self.screen.marker_centre_x()
        self.assertAlmostEqual(coarse, fine, delta=0.5)

    def test_marker_scales_with_screen_width(self):
        small = self.marker_x_at(goal_index=1, progress=0.5)
        self.screen.width, self.screen.height = 320, 240
        big = self.marker_x_at(goal_index=1, progress=0.5)
        self.assertAlmostEqual(big, small * 2, delta=1.0)


class StateTests(ScreenTestCase):
    def test_in_range_and_out_of_range_look_different(self):
        self.settle(vm(), frames=3)
        self.frame(vm())
        near = list(self.screen.calls)
        near_texts = self.screen.texts()

        self.mod.reset()
        away = vm(in_range=False, last_shared_total=1200, own_new_steps=300, seconds_since_share=180)
        self.settle(away, frames=3)
        self.frame(away)
        far = list(self.screen.calls)
        far_texts = self.screen.texts()

        self.assertIn("IN RANGE", near_texts)
        self.assertNotIn("OUT OF RANGE", near_texts)
        self.assertIn("OUT OF RANGE", far_texts)
        self.assertNotIn("IN RANGE", far_texts)
        self.assertNotEqual({c[1] for c in near if c[0] != "text"}, {c[1] for c in far if c[0] != "text"})

    def test_out_of_range_marker_uses_the_faded_sprite_row(self):
        self.frame(vm())
        (near,) = self.screen.markers()
        self.mod.reset()
        self.frame(vm(in_range=False))
        (far,) = self.screen.markers()
        self.assertNotEqual(near[3].row, far[3].row)

    def test_out_of_range_shows_time_since_share_and_own_new_steps(self):
        self.frame(vm(in_range=False, last_shared_total=1200, own_new_steps=300, seconds_since_share=180))
        texts = self.screen.texts()
        self.assertIn("APART 3M AGO", texts)
        self.assertIn("+300", texts)
        self.assertIn("1200", texts)
        self.assertNotIn("1500", texts)

    def test_in_range_shows_pooled_total(self):
        self.frame(vm(pooled_total=1950))
        self.assertIn("1950", self.screen.texts())
        self.assertFalse([t for t in self.screen.texts() if t.startswith("+")])

    def test_upcoming_goal_and_steps_to_next_are_shown(self):
        self.frame(vm(goal="Old oak", steps_to_next=550))
        self.assertTrue(any("OLD OAK" in t and "550" in t for t in self.screen.texts()))

    def test_never_shared_while_apart_says_so(self):
        self.frame(vm(in_range=False, seconds_since_share=None))
        self.assertIn("NO SHARE YET", self.screen.texts())

    def test_reaching_a_goal_shows_a_banner_that_expires(self):
        self.frame(vm(goal_index=0, progress=0.99, goal="Meadow gate", last_goal=None))
        self.assertFalse([t for t in self.screen.texts() if "REACHED" in t])
        self.frame(vm(goal_index=1, progress=0.0, goal="Old oak", last_goal="Meadow gate"))
        self.assertIn("REACHED MEADOW GATE!", self.screen.texts())
        self.frame(vm(goal_index=1, progress=0.0, goal="Old oak", last_goal="Meadow gate"), dt=1000)
        self.assertIn("REACHED MEADOW GATE!", self.screen.texts())
        for _ in range(4):
            self.frame(vm(goal_index=1, progress=0.0, goal="Old oak", last_goal="Meadow gate"), dt=1000)
        self.assertFalse([t for t in self.screen.texts() if "REACHED" in t])

    def test_starting_on_a_later_goal_does_not_celebrate(self):
        self.frame(vm(goal_index=3, last_goal="Windmill"))
        self.assertFalse([t for t in self.screen.texts() if "REACHED" in t])

    def test_finished_walk_keeps_a_completion_banner(self):
        done = vm(goal_index=5, progress=1.0, goal=None, steps_to_next=0, last_goal="Hilltop", pooled_total=12500)
        self.frame(done)
        self.settle(done, frames=20, dt=1000)
        self.assertIn("ALL GOALS REACHED!", self.screen.texts())


class FormatTests(ScreenTestCase):
    def test_format_ago(self):
        ago = self.mod.format_ago
        self.assertEqual(ago(0), "0S AGO")
        self.assertEqual(ago(59), "59S AGO")
        self.assertEqual(ago(60), "1M AGO")
        self.assertEqual(ago(180), "3M AGO")
        self.assertEqual(ago(3599), "59M AGO")
        self.assertEqual(ago(7300), "2H AGO")
        self.assertEqual(ago(None), "NO SHARE YET")


class RuntimeRuleTests(ScreenTestCase):
    def test_assets_load_once_at_import_not_per_frame(self):
        loaded = list(self.images.loads)
        self.assertTrue(loaded)
        self.assertTrue(all(p.startswith("assets/") and p.endswith(".png") for p in loaded))
        fonts_after_import = self.fonts.accesses
        self.settle(vm(), frames=30)
        self.settle(vm(in_range=False, own_new_steps=3), frames=30)
        self.assertEqual(self.images.loads, loaded)
        self.assertEqual(self.fonts.accesses, fonts_after_import)

    def test_orientation_does_not_change_drawing(self):
        self.badge.flipped = False
        self.settle(vm(), frames=5)
        self.frame(vm())
        upright = list(self.screen.calls)

        self.mod.reset()
        self.badge.flipped = True
        self.settle(vm(), frames=5)
        self.frame(vm())
        self.assertEqual(upright, self.screen.calls)

    def check_layout_fits(self):
        w, h = self.screen.width, self.screen.height
        models = (
            vm(),
            vm(in_range=False, last_shared_total=123456, own_new_steps=9999, seconds_since_share=7300, goal="River bridge", steps_to_next=7999),
            vm(goal_index=2, last_goal="River bridge"),
        )
        for model in models:
            self.mod.reset()
            self.frame(model)
            self.frame(dict(model, goal_index=model["goal_index"] + 1, last_goal="River bridge"))
            for c in self.screen.calls:
                if c[0] == "text":
                    _, _, _, text, x, y, size = c
                    tw, th = self.screen.measure_text(text, size)
                    self.assertGreaterEqual(x, 0, text)
                    self.assertLessEqual(x + tw, w, text)
                    self.assertLessEqual(y + th, h, text)
                elif c[0] == "blit":
                    dest = c[4]
                    if dest[0] == "rect":
                        _, x, y, rw, rh = dest
                        self.assertGreaterEqual(x, 0)
                        self.assertGreaterEqual(y, 0)
                        self.assertLessEqual(x + rw, w + 0.001)
                        self.assertLessEqual(y + rh, h + 0.001)

    def test_layout_fits_at_160x120(self):
        self.check_layout_fits()

    def test_layout_fits_at_320x240(self):
        self.screen.width, self.screen.height = 320, 240
        self.check_layout_fits()

    def test_count_text_is_larger_than_status_text(self):
        self.frame(vm())
        sizes = {c[3]: c[6] for c in self.screen.calls if c[0] == "text"}
        self.assertGreater(sizes["1950"], sizes["IN RANGE"])


class ViewModelTests(unittest.TestCase):
    def setUp(self):
        sys.modules.pop("screen", None)
        self.led = ledger.Ledger()
        self.led.add_steps(700)
        self.led.pair(0xB2)
        self.led.receive(0xB2, 500, 1000)

    def build(self, in_range, now):
        # build_view_model is pure; it needs no badge globals.
        import builtins as b

        saved = {n: getattr(b, n, None) for n in GLOBALS}
        b.image, b.font, b.color = FakeImageNs(), FakeFontNs(), FakeColor
        b.shape, b.vec2, b.rect = FakeShape(), vec2, rect
        try:
            mod = importlib.import_module("screen")
            return mod.build_view_model(self.led, in_range, now)
        finally:
            for n, v in saved.items():
                if v is None:
                    if hasattr(b, n):
                        delattr(b, n)
                else:
                    setattr(b, n, v)
            sys.modules.pop("screen", None)

    def test_in_range_view_model_comes_from_the_ledger(self):
        model = self.build(True, 5000)
        self.assertEqual(model["pooled_total"], 1200)
        self.assertEqual(model["goal"], self.led.goal_info()["goal"])
        self.assertEqual(model["steps_to_next"], self.led.goal_info()["steps_to_next"])
        self.assertEqual(model["progress"], self.led.goal_info()["progress"])
        self.assertEqual(model["goal_index"], self.led.goal_info()["index"])
        self.assertEqual(model["goal_count"], len(self.led.goals))
        self.assertEqual(model["seconds_since_share"], 4)
        self.assertTrue(model["in_range"])

    def test_apart_view_model_reports_last_shared_and_own_new_steps(self):
        self.led.add_steps(300)
        model = self.build(False, 61000)
        self.assertEqual(model["last_shared_total"], 1200)
        self.assertEqual(model["own_new_steps"], 300)
        self.assertEqual(model["pooled_total"], 1500)
        self.assertEqual(model["seconds_since_share"], 60)
        self.assertFalse(model["in_range"])

    def test_view_model_names_the_last_goal_reached(self):
        self.led = ledger.Ledger()
        self.assertIsNone(self.build(True, 0)["last_goal"])
        self.led.add_steps(self.led.goals[0][1])
        self.assertEqual(self.build(True, 0)["last_goal"], self.led.goals[0][0])

    def test_unpaired_ledger_has_no_share_time(self):
        self.led = ledger.Ledger()
        self.assertIsNone(self.build(False, 100)["seconds_since_share"])


if __name__ == "__main__":
    unittest.main()
