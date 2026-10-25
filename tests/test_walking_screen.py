import builtins
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "badge", "apps", "walking"))
import layout  # noqa: E402
from ledger import GOAL, Ledger  # noqa: E402


def make(confirmed, pending=0, partner="maggie"):
    return Ledger.from_dict(
        {
            "me": "martin",
            "contributions": {"martin": confirmed or 0},
            "confirmed_total": confirmed,
            "partner": partner if confirmed is not None else None,
            "pending": pending,
        }
    )


def fake_measure(text, size):
    return int(len(text) * size * 0.6)


class FormatTests(unittest.TestCase):
    def test_commas(self):
        self.assertEqual(layout.format_count(0), "0")
        self.assertEqual(layout.format_count(999), "999")
        self.assertEqual(layout.format_count(9900), "9,900")
        self.assertEqual(layout.format_count(1000025), "1,000,025")

    def test_partner_alpha_is_055(self):
        self.assertEqual(layout.PARTNER_ALPHA, 0.55)
        self.assertEqual(layout.alpha_byte(0.55), 140)


class ViewModelTests(unittest.TestCase):
    def test_walking_with_pending(self):
        vm = layout.view_model(make(9900, 60))
        self.assertEqual(vm["big_text"], "9,900")
        self.assertEqual(vm["plus_text"], "+60")
        self.assertEqual(vm["caption"], "of 10,000 shared steps")
        self.assertEqual(vm["goal_state"], "near")
        self.assertFalse(vm["lighthouse_lit"])
        self.assertEqual(vm["status_text"], "Walking with Maggie")
        self.assertFalse(vm["warning"])

    def test_apart_and_up_to_date_hides_plus_zero(self):
        vm = layout.view_model(make(4200, 0))
        self.assertEqual(vm["big_text"], "4,200")
        self.assertIsNone(vm["plus_text"])
        self.assertEqual(vm["goal_state"], "walking")

    def test_first_use_shows_own_steps_not_a_team_total(self):
        vm = layout.view_model(make(None, 120))
        self.assertTrue(vm["first_use"])
        self.assertEqual(vm["caption"], "Your steps, not synced yet")
        self.assertEqual(vm["big_text"], "120")
        self.assertIsNone(vm["plus_text"])
        self.assertNotIn("10,000", vm["caption"])
        self.assertFalse(vm["show_partner"])
        self.assertFalse(vm["lighthouse_lit"])
        self.assertEqual(vm["goal_state"], "none")

    def test_confirmed_zero_is_not_first_use(self):
        vm = layout.view_model(make(0, 0))
        self.assertFalse(vm["first_use"])
        self.assertEqual(vm["big_text"], "0")
        self.assertEqual(vm["caption"], "of 10,000 shared steps")
        self.assertEqual(vm["progress"], 0.0)

    def test_goal_states_and_lighthouse(self):
        self.assertEqual(layout.view_model(make(9000))["goal_state"], "near")
        self.assertFalse(layout.view_model(make(GOAL - 1))["lighthouse_lit"])
        at = layout.view_model(make(GOAL))
        self.assertEqual(at["goal_state"], "reached")
        self.assertTrue(at["lighthouse_lit"])
        self.assertEqual(at["progress"], 1.0)
        past = layout.view_model(make(10300, 5))
        self.assertTrue(past["lighthouse_lit"])
        self.assertEqual(past["big_text"], "10,300")
        self.assertEqual(past["progress"], 1.0)

    def test_pending_steps_never_light_the_lighthouse(self):
        vm = layout.view_model(make(9900, 500))
        self.assertFalse(vm["lighthouse_lit"])
        self.assertFalse(layout.view_model(make(None, 50000))["lighthouse_lit"])

    def test_partner_is_faded(self):
        vm = layout.view_model(make(500))
        self.assertTrue(vm["show_partner"])
        self.assertEqual(vm["partner_alpha"], 0.55)

    def test_warnings_replace_status_and_keep_saved_total(self):
        cases = (
            (layout.WARN_SYNC_UNAVAILABLE, "! Sync unavailable"),
            (layout.WARN_SENSOR_UNAVAILABLE, "! Step sensor unavailable"),
            (layout.WARN_NOT_SAVED, "! Progress not saved"),
        )
        for warning, text in cases:
            vm = layout.view_model(make(9900, 60), warning)
            self.assertEqual(vm["status_text"], text)
            self.assertTrue(vm["warning"])
            self.assertEqual(vm["big_text"], "9,900")
            self.assertEqual(vm["plus_text"], "+60")


class FitTests(unittest.TestCase):
    SIZES = [60, 40, 20, 10]

    def test_pair_shares_size_and_is_centred_jointly(self):
        size, tx, px, w = layout.fit_pair("9,900", "+60", self.SIZES, fake_measure, 296, 160)
        self.assertEqual(w, fake_measure("9,900", size) + layout.PAIR_GAP + fake_measure("+60", size))
        self.assertEqual(tx, 160 - w // 2)
        self.assertEqual(px, tx + fake_measure("9,900", size) + layout.PAIR_GAP)

    def test_no_plus_centres_total_alone(self):
        size, tx, px, w = layout.fit_pair("9,900", None, self.SIZES, fake_measure, 296, 160)
        self.assertIsNone(px)
        self.assertEqual(tx, 160 - fake_measure("9,900", size) // 2)

    def test_plus_forces_a_smaller_size_than_total_alone(self):
        alone = layout.fit_pair("1,000,025", None, self.SIZES, fake_measure, 296, 160)[0]
        both = layout.fit_pair("1,000,025", "+1,234", self.SIZES, fake_measure, 296, 160)[0]
        self.assertGreater(alone, both)

    def test_large_count_shrinks_to_fit(self):
        size, tx, px, w = layout.fit_pair("1,000,025", "+12", self.SIZES, fake_measure, 296, 160)
        self.assertLessEqual(w, 296)
        self.assertLess(size, 60)
        self.assertGreaterEqual(tx, 12)

    def test_smallest_size_used_when_nothing_fits(self):
        size = layout.fit_pair("1,000,025", "+1,000,000", [60, 40], fake_measure, 50, 160)[0]
        self.assertEqual(size, 40)


class StubFont:
    def __init__(self, name, height):
        self.name = name
        self.height = height


class StubScreen:
    width = 320
    height = 240

    def __init__(self):
        self.font = None
        self.pen = None
        self.calls = []

    def measure_text(self, text):
        return (int(len(text) * self.font.height * 0.6), self.font.height)

    def text(self, text, x, y):
        self.calls.append(("text", text, x, y, self.font, self.pen))

    def rectangle(self, r):
        self.calls.append(("rectangle", r, self.pen))

    def shape(self, s):
        self.calls.append(("shape", s, self.pen))

    def line(self, *args):
        self.calls.append(("line", args, self.pen))


class StubBadge:
    ticks_delta = 16

    def mode(self, mode):
        self.last_mode = mode


class StubFonts:
    nope = StubFont("nope", 60)
    sins = StubFont("sins", 40)
    ark = StubFont("ark", 20)
    ziplock = StubFont("ziplock", 12)


class StubColor:
    @staticmethod
    def rgb(r, g, b, a=255):
        return (r, g, b, a)


class StubShape:
    @staticmethod
    def rounded_rectangle(x, y, w, h, r):
        return ("rrect", x, y, w, h, r)


LIGHT_ON_PEN = (255, 222, 110, 255)


class DrawSmokeTests(unittest.TestCase):
    """Runs the real renderer against recording stubs. Not an on-device check."""

    @classmethod
    def setUpClass(cls):
        cls.names = ("badge", "screen", "font", "color", "shape", "rect", "HIRES", "VSYNC")
        cls.saved = dict((n, getattr(builtins, n, None)) for n in cls.names)
        cls.screen = StubScreen()
        cls.badge = StubBadge()
        builtins.badge = cls.badge
        builtins.screen = cls.screen
        builtins.font = StubFonts
        builtins.color = StubColor
        builtins.shape = StubShape
        builtins.rect = lambda x, y, w, h: ("rect", x, y, w, h)
        builtins.HIRES = 2
        builtins.VSYNC = 1
        sys.modules.pop("main_screen", None)
        import main_screen

        cls.ms = main_screen

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop("main_screen", None)
        for n, v in cls.saved.items():
            if v is None:
                delattr(builtins, n)
            else:
                setattr(builtins, n, v)

    def render(self, ledger, warning=None):
        self.screen.calls = []
        self.ms.draw(ledger, warning)
        return self.screen.calls

    def texts(self, calls, text):
        """Foreground (non-shadow) draws of this text."""
        found = [c for c in calls if c[0] == "text" and c[1] == text]
        return [c for c in found if c[5] != self.ms.SHADOW]

    def test_requests_hires_mode(self):
        self.assertEqual(self.badge.last_mode, 2 | 1)

    def test_every_fixture_draws_with_count_and_caption(self):
        fixtures = [
            make(9900, 60),
            make(4200, 0),
            make(None, 120),
            make(0, 0),
            make(9000, 0),
            make(GOAL, 0),
            make(10300, 5),
            make(1000025, 0),
            make(1000025, 12),
        ]
        for led in fixtures:
            vm = layout.view_model(led)
            calls = self.render(led)
            self.assertEqual(len(self.texts(calls, vm["big_text"])), 1, vm["big_text"])
            self.assertEqual(len(self.texts(calls, vm["caption"])), 1)

    def test_plus_shares_total_baseline_size_and_pen_is_amber(self):
        calls = self.render(make(9900, 60))
        total = self.texts(calls, "9,900")[0]
        plus = self.texts(calls, "+60")[0]
        self.assertEqual(total[3], plus[3])  # same y
        self.assertIs(total[4], plus[4])  # same font
        self.assertEqual(plus[5], self.ms.AMBER)
        self.assertGreater(plus[2], total[2])

    def test_plus_zero_is_not_drawn(self):
        calls = self.render(make(4200, 0))
        self.assertFalse([c for c in calls if c[0] == "text" and c[1].startswith("+")])

    def test_large_count_stays_between_status_and_caption(self):
        for led in (make(1000025, 0), make(1000025, 12)):
            vm = layout.view_model(led)
            calls = self.render(led)
            total = self.texts(calls, vm["big_text"])[0]
            width = int(len(vm["big_text"]) * total[4].height * 0.6)
            if vm["plus_text"]:
                plus = self.texts(calls, vm["plus_text"])[0]
                right = plus[2] + int(len(vm["plus_text"]) * plus[4].height * 0.6)
            else:
                right = total[2] + width
            self.assertGreaterEqual(total[2], self.ms.MARGIN)
            self.assertLessEqual(right, self.screen.width - self.ms.MARGIN)
            status = self.texts(calls, vm["status_text"])[0]
            self.assertLessEqual(status[3] + status[4].height, total[3])
            self.assertLessEqual(total[3] + total[4].height, self.texts(calls, vm["caption"])[0][3])

    def test_animation_advances_with_ticks_delta(self):
        led = make(500)
        self.badge.ticks_delta = 16
        first = self.render(led)
        self.badge.ticks_delta = 100
        second = self.render(led)
        self.badge.ticks_delta = 16
        legs = lambda calls: [c[1] for c in calls if c[0] == "shape" and c[1][3] == 3]
        self.assertNotEqual(legs(first), legs(second))

    def test_first_use_big_number_is_amber(self):
        calls = self.render(make(None, 120))
        self.assertEqual(self.texts(calls, "120")[0][5], self.ms.AMBER)
        self.assertEqual(len(self.texts(calls, "Your steps, not synced yet")), 1)

    def test_lighthouse_lit_only_for_confirmed_goal(self):
        def lit(calls):
            return any(c[0] == "rectangle" and c[2] == LIGHT_ON_PEN for c in calls)

        self.assertFalse(lit(self.render(make(9900, 5000))))
        self.assertFalse(lit(self.render(make(None, 50000))))
        self.assertTrue(lit(self.render(make(GOAL, 0))))
        self.assertTrue(lit(self.render(make(10300, 0))))

    def test_partner_drawn_faded_at_alpha_055(self):
        faded = (self.ms.PARTNER_PALETTE["body"])
        self.assertEqual(faded[3], 140)

        def faded_shapes(calls):
            return [c for c in calls if c[0] == "shape" and c[2][3] == 140]

        self.assertTrue(faded_shapes(self.render(make(500))))
        self.assertFalse(faded_shapes(self.render(make(None, 20))))

    def test_warning_shows_on_status_line_and_keeps_total(self):
        calls = self.render(make(9900, 60), layout.WARN_NOT_SAVED)
        status = self.texts(calls, "! Progress not saved")
        self.assertEqual(len(status), 1)
        self.assertEqual(status[0][5], self.ms.WARN)
        self.assertEqual(len(self.texts(calls, "9,900")), 1)
        self.assertEqual(len(self.texts(calls, "+60")), 1)


if __name__ == "__main__":
    unittest.main()
