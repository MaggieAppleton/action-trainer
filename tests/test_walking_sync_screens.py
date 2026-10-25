import builtins
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "badge", "apps", "walking"))
import layout  # noqa: E402
import sync  # noqa: E402
import sync_layout  # noqa: E402
from ledger import Ledger  # noqa: E402
from sync import Session  # noqa: E402

try:
    from test_walking_sync import Pair  # python -m unittest discover -s tests
except ImportError:
    from tests.test_walking_sync import Pair  # python -m unittest tests.test_...

ACTIVE = (sync.HOLD, sync.CONNECTING, sync.EXCHANGE, sync.AWAITING_ACK)
BEFORE_SUCCESS = ACTIVE + (sync.RETRY,)
GOAL_CAPTION = sync_layout.TOTAL_CAPTION  # "of 10,000 shared steps" mentions the goal, not a total


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
    ticks_delta = 100

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


class IdleTransport:
    def __init__(self, up=True):
        self.up = up

    def connected(self):
        return self.up

    def send(self, data):
        pass

    def receive(self):
        return None


def lone_session(confirmed, pending, state, **attrs):
    """A session parked in a state by hand, for screens that are awkward to reach."""
    led = Ledger.from_dict(
        {
            "me": "martin",
            "contributions": {"martin": confirmed or 0},
            "confirmed_total": confirmed,
            "partner": "maggie" if confirmed is not None else None,
            "pending": pending,
        }
    )
    s = Session(led, IdleTransport())
    s.state = state
    for k, v in attrs.items():
        setattr(s, k, v)
    return s


class Base(unittest.TestCase):
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
        for name in ("main_screen", "sync_screens"):
            sys.modules.pop(name, None)
        import main_screen
        import sync_screens

        cls.ms = main_screen
        cls.ss = sync_screens

    @classmethod
    def tearDownClass(cls):
        for name in ("main_screen", "sync_screens"):
            sys.modules.pop(name, None)
        for n, v in cls.saved.items():
            if v is None:
                delattr(builtins, n)
            else:
                setattr(builtins, n, v)

    def setUp(self):
        self.badge.ticks_delta = 100
        self.ss._last_state = None
        self.ss._celebration_ms = 0

    def render(self, session, warning=None):
        self.screen.calls = []
        self.ss.draw(session, warning)
        return self.screen.calls

    def texts(self, calls):
        """Foreground (non-shadow) text draws."""
        return [c for c in calls if c[0] == "text" and c[5] != self.ms.SHADOW]

    def strings(self, calls):
        return [c[1] for c in self.texts(calls)]

    def confetti(self, calls):
        rgbs = set(sync_layout.CONFETTI_RGB)
        return [c for c in calls if c[0] == "rectangle" and c[2][:3] in rgbs and c[1][3] <= 12]

    def assert_text_fits(self, calls):
        """Every text is on screen and no two lines overlap."""
        rects = []
        for _, text, x, y, f, _pen in self.texts(calls):
            w = int(len(text) * f.height * 0.6)
            self.assertGreaterEqual(x, 0, text)
            self.assertLessEqual(x + w, self.screen.width, text)
            self.assertGreaterEqual(y, 0, text)
            self.assertLessEqual(y + f.height, self.screen.height, text)
            rects.append((text, y, y + f.height))
        for i, (ta, ya, ea) in enumerate(rects):
            for tb, yb, eb in rects[i + 1 :]:
                if ya == yb:
                    continue  # the total and its +N share a line
                self.assertTrue(ea <= yb or eb <= ya, "%r overlaps %r" % (ta, tb))

    def assert_no_new_total(self, calls, new="10,000"):
        for text in self.strings(calls):
            stripped = text.replace(GOAL_CAPTION, "")
            self.assertNotIn(new, stripped, text)
            self.assertNotIn("+100", stripped, text)
            self.assertNotIn("Synced", text)
            self.assertNotIn("made it", text)


def settle_first_sync(p):
    """Martin (b) brings 9,900 and shares it, then the badges separate."""
    p.lb.add_steps(9900)
    p.sync(8000)
    p.separate()


class CanonicalFixtureTests(Base):
    """Martin 9,900, Maggie +60, Martin +40, driven through real sessions."""

    def run_fixture(self):
        p = Pair()
        settle_first_sync(p)
        p.la.add_steps(60)
        p.lb.add_steps(40)
        self.assertEqual((p.la.confirmed_total, p.lb.confirmed_total), (9900, 9900))
        p.hold()
        frames = {"a": [], "b": []}
        for _ in range(80):
            p.step()
            for key, s in (("a", p.a), ("b", p.b)):
                frames[key].append((s.state, sync_layout.view_model(s), self.render(s)))
        p.separate()
        return p, frames

    def test_every_state_is_visited_and_drawn_for_both_badges(self):
        p, frames = self.run_fixture()
        want = [sync.HOLD, sync.CONNECTING, sync.EXCHANGE, sync.AWAITING_ACK, sync.SUCCESS, sync.SEPARATE]
        for key in ("a", "b"):
            seen = []
            for state, vm, calls in frames[key]:
                if not seen or seen[-1] != state:
                    seen.append(state)
                self.assertTrue(vm["title"], state)
                self.assertTrue(self.strings(calls), state)
                self.assert_text_fits(calls)
            self.assertEqual(seen, want)

    def test_nothing_shows_the_new_total_before_success(self):
        _, frames = self.run_fixture()
        for key, pending in (("a", "+60"), ("b", "+40")):
            checked = 0
            for state, vm, calls in frames[key]:
                if state in sync.STATES and state not in (sync.SUCCESS, sync.SEPARATE):
                    checked += 1
                    self.assertEqual(vm["total_text"], "9,900", state)
                    self.assertEqual(vm["plus_text"], pending, state)
                    self.assertFalse(vm["show_total_is_new"], state)
                    self.assertFalse(vm["celebrate"], state)
                    self.assert_no_new_total(calls)
                    strings = self.strings(calls)
                    self.assertEqual(strings.count("9,900"), 1, state)
                    self.assertEqual(strings.count(pending), 1, state)
            self.assertGreaterEqual(checked, 10)

    def test_active_screens_use_the_approved_titles(self):
        _, frames = self.run_fixture()
        titles = {}
        for state, vm, calls in frames["b"]:
            titles[state] = vm["title"]
            if state in ACTIVE:
                self.assertIn(vm["title"], self.strings(calls))
        self.assertEqual(titles[sync.HOLD], "Holding steady")
        self.assertEqual(titles[sync.CONNECTING], "Connecting")
        self.assertEqual(titles[sync.EXCHANGE], "Swapping steps")
        self.assertEqual(titles[sync.AWAITING_ACK], "Waiting for acknowledgement")

    def test_active_screens_draw_the_amber_plus_and_previous_total(self):
        _, frames = self.run_fixture()
        for state, vm, calls in frames["b"]:
            if state not in ACTIVE:
                continue
            by_text = dict((c[1], c) for c in self.texts(calls))
            self.assertEqual(by_text["+40"][5], self.ms.AMBER)
            self.assertEqual(by_text["9,900"][5], self.ms.WHITE)
            self.assertEqual(by_text["+40"][3], by_text["9,900"][3])

    def test_success_is_a_full_screen_celebration_with_new_total_and_added(self):
        _, frames = self.run_fixture()
        for key in ("a", "b"):
            successes = [(vm, calls) for state, vm, calls in frames[key] if state == sync.SUCCESS]
            self.assertTrue(successes)
            for vm, calls in successes:
                self.assertTrue(vm["celebrate"])
                self.assertTrue(vm["check"])
                self.assertTrue(vm["show_total_is_new"])
                self.assertTrue(vm["goal_reached"])  # 9,900 -> 10,000
                self.assertEqual(vm["title"], "You made it!")
                self.assertEqual(vm["total_text"], "10,000")
                self.assertEqual(vm["subtitle"], "+100 together")
                strings = self.strings(calls)
                for text in ("You made it!", "10,000", "+100 together"):
                    self.assertEqual(strings.count(text), 1, text)
                self.assertNotIn("9,900", strings)
                self.assertIsNone(vm["plus_text"])
                self.assert_text_fits(calls)
                # dimmed scene: a translucent night-coloured cover over the whole screen
                cover = [c for c in calls if c[0] == "rectangle" and c[1] == self.ms.DIM_RECT]
                self.assertEqual(len(cover), 1)
                self.assertEqual(cover[0][2][3], int(self.ss.DIM_SUCCESS * 255 + 0.5))
                # check mark: a circle plus strokes
                self.assertTrue([c for c in calls if c[0] == "shape" and c[1][0] == "rrect" and c[1][3] == self.ss.CHECK_SIZE])
                self.assertTrue([c for c in calls if c[0] == "line"])

    def test_then_prompts_to_move_apart_and_returns_to_walking_after_disconnect(self):
        p, frames = self.run_fixture()
        for key in ("a", "b"):
            seps = [(vm, calls) for state, vm, calls in frames[key] if state == sync.SEPARATE]
            self.assertTrue(seps)
            for vm, calls in seps:
                self.assertEqual(vm["title"], "Move badges apart")
                self.assertFalse(vm["celebrate"])
                self.assertEqual(vm["total_text"], "10,000")
                strings = self.strings(calls)
                self.assertIn("Move badges apart", strings)
                self.assertIn("10,000", strings)
                self.assertEqual(self.confetti(calls), [])
                self.assert_text_fits(calls)
        # the transport disconnected: the screen is the walking main screen again
        for s in (p.a, p.b):
            self.assertEqual(s.state, sync.WALKING)
            calls = self.render(s)
            expected = "Walking with " + ("Martin" if s is p.a else "Maggie")
            strings = self.strings(calls)
            self.assertIn(expected, strings)
            self.assertIn("10,000", strings)
            self.assertIn(GOAL_CAPTION, strings)
            self.assertNotIn("Move badges apart", strings)
            self.assertNotIn("Synced!", strings)
            self.assertEqual(self.confetti(calls), [])

    def test_separate_stays_until_the_transport_disconnects(self):
        p = Pair()
        settle_first_sync(p)
        p.la.add_steps(60)
        p.lb.add_steps(40)
        p.sync(8000)  # link still up
        self.assertEqual(p.b.state, sync.SEPARATE)
        self.assertIn("Move badges apart", self.strings(self.render(p.b)))
        p.run(10000)
        self.assertEqual(p.b.state, sync.SEPARATE)
        self.assertIn("Move badges apart", self.strings(self.render(p.b)))
        p.separate()
        self.assertNotIn("Move badges apart", self.strings(self.render(p.b)))


class RetryScreenTests(Base):
    def synced_pair(self):
        p = Pair()
        settle_first_sync(p)
        p.la.add_steps(60)
        p.lb.add_steps(40)
        return p

    def test_moving_apart_too_soon_keeps_total_and_pending(self):
        p = self.synced_pair()
        p.hold()
        for _ in range(80):
            p.step()
            if p.a.state == sync.EXCHANGE:
                p.link.sever()
        self.assertEqual(p.a.state, sync.RETRY)
        for s, pending in ((p.a, "+60"), (p.b, "+40")):
            calls = self.render(s)
            vm = sync_layout.view_model(s)
            strings = self.strings(calls)
            self.assertEqual(vm["title"], "Sync didn't finish")
            self.assertEqual(strings.count("9,900"), 1)
            self.assertEqual(strings.count(pending), 1)
            self.assertIn("Still 9,900 shared steps", strings)
            self.assertIn("Badges moved apart too soon", strings)
            self.assert_no_new_total(calls)
            self.assert_text_fits(calls)

    def test_timeout_reads_timed_out(self):
        p = self.synced_pair()
        p.link.up = False  # never connects
        p.a.begin_hold()
        p.b.begin_hold()
        p.run(10000)
        self.assertEqual(p.a.state, sync.RETRY)
        calls = self.render(p.b)
        strings = self.strings(calls)
        self.assertIn("Timed out", strings)
        self.assertIn("Still 9,900 shared steps", strings)
        self.assertIn("+40", strings)
        self.assert_no_new_total(calls)

    def test_other_reasons_say_try_again(self):
        for reason in (sync.REASON_MISMATCH, sync.REASON_SEND_FAILED, sync.REASON_CANCELLED, None):
            s = lone_session(9900, 60, sync.RETRY, retry_reason=reason)
            strings = self.strings(self.render(s))
            self.assertIn("Try again", strings)
            self.assertIn("Still 9,900 shared steps", strings)
            self.assertIn("9,900", strings)
            self.assertIn("+60", strings)

    def test_first_use_retry_does_not_fabricate_a_total(self):
        s = lone_session(None, 120, sync.RETRY, retry_reason=sync.REASON_DROPPED)
        calls = self.render(s)
        vm = sync_layout.view_model(s)
        strings = self.strings(calls)
        self.assertEqual(vm["subtitle"], "Your steps, not synced yet")
        self.assertIn("Your steps, not synced yet", strings)
        self.assertIn("Badges moved apart too soon", strings)
        self.assertEqual(vm["total_text"], "120")
        self.assertIsNone(vm["plus_text"])
        self.assertTrue(vm["unshared_total"])
        self.assertEqual([c for c in self.texts(calls) if c[1] == "120"][0][5], self.ms.AMBER)
        for text in strings:
            self.assertNotIn("Still", text)
            self.assertNotIn("10,000", text)

    def test_first_use_hold_does_not_fabricate_a_total(self):
        s = lone_session(None, 120, sync.HOLD)
        strings = self.strings(self.render(s))
        self.assertIn("Holding steady", strings)
        self.assertIn("Your steps, not synced yet", strings)
        self.assertIn("120", strings)
        for text in strings:
            self.assertNotIn("10,000", text)


class UpToDateTests(Base):
    def test_up_to_date_keeps_total_and_shows_nothing_new(self):
        p = Pair()
        settle_first_sync(p)
        p.sync(1500)  # nothing new on either side
        self.assertEqual(p.b.state, sync.UP_TO_DATE)
        for s in (p.a, p.b):
            vm = sync_layout.view_model(s)
            calls = self.render(s)
            strings = self.strings(calls)
            self.assertEqual(vm["title"], "Already up to date")
            self.assertIn("Already up to date", strings)
            self.assertIn("9,900", strings)
            self.assertFalse(vm["celebrate"])
            self.assertEqual(self.confetti(calls), [])
            self.assertNotIn("Synced!", strings)
            self.assert_text_fits(calls)

    def test_up_to_date_keeps_pending_steps_taken_meanwhile(self):
        s = lone_session(9900, 7, sync.UP_TO_DATE)
        strings = self.strings(self.render(s))
        self.assertIn("9,900", strings)
        self.assertIn("+7", strings)


class AllStatesTests(Base):
    def test_every_state_has_a_screen_that_fits(self):
        for confirmed, pending in ((9900, 60), (4200, 0), (None, 120), (0, 0), (1000025, 12)):
            for state in sync.STATES:
                attrs = {}
                if state in (sync.SUCCESS, sync.SEPARATE):
                    attrs = {"result_total": (confirmed or 0) + 100, "result_added": 100, "previous_total": confirmed}
                s = lone_session(confirmed, pending, state, **attrs)
                if state in (sync.SUCCESS, sync.SEPARATE):
                    s.ledger.confirmed_total = attrs["result_total"]
                calls = self.render(s)
                self.assertTrue(self.texts(calls), state)
                self.assert_text_fits(calls)

    def test_walking_delegates_to_the_main_screen(self):
        s = lone_session(9900, 60, sync.WALKING)
        calls = self.render(s)
        self.screen.calls = []
        self.ms.draw(s.ledger)
        self.assertEqual(self.strings(calls), self.strings(self.screen.calls))

    def test_walking_passes_warning_through(self):
        s = lone_session(9900, 60, sync.WALKING)
        strings = self.strings(self.render(s, layout.WARN_NOT_SAVED))
        self.assertIn("! Progress not saved", strings)

    def test_quiet_inline_synced_label_is_not_used(self):
        for state in sync.STATES:
            if state in (sync.SUCCESS,):
                continue
            s = lone_session(9900, 60, state, result_total=10000, result_added=100, previous_total=9900)
            for text in self.strings(self.render(s)):
                self.assertNotEqual(text.lower(), "synced")

    def test_celebration_text_comes_from_result_total(self):
        s = lone_session(
            9900, 0, sync.SUCCESS, result_total=10300, result_added=400, previous_total=9900
        )
        vm = sync_layout.view_model(s)
        self.assertEqual(vm["total_text"], "10,300")
        self.assertEqual(vm["subtitle"], "+400 together")


class GoalTests(Base):
    def test_goal_reached_only_when_crossing_from_below(self):
        self.assertTrue(sync_layout.goal_reached(9900, 10000))
        self.assertTrue(sync_layout.goal_reached(9900, 10300))
        self.assertTrue(sync_layout.goal_reached(None, 10000))
        self.assertFalse(sync_layout.goal_reached(10000, 10100))
        self.assertFalse(sync_layout.goal_reached(9000, 9900))
        self.assertFalse(sync_layout.goal_reached(9900, None))

    def test_success_below_goal_says_synced(self):
        p = Pair()
        p.lb.add_steps(4000)
        p.sync(8000)
        s = p.b
        self.assertEqual(s.state, sync.SEPARATE)
        # replay the success screen from the first sync's result
        s.state = sync.SUCCESS
        vm = sync_layout.view_model(s)
        self.assertEqual(vm["title"], "Synced!")
        self.assertFalse(vm["goal_reached"])
        self.assertEqual(vm["total_text"], "4,000")
        self.assertEqual(vm["subtitle"], "+4,000 together")
        strings = self.strings(self.render(s))
        self.assertIn("Synced!", strings)
        self.assertNotIn("You made it!", strings)

    def test_goal_screen_lights_the_lighthouse_behind_the_celebration(self):
        s = lone_session(10000, 0, sync.SUCCESS, result_total=10000, result_added=100, previous_total=9900)
        calls = self.render(s)
        self.assertTrue(any(c[0] == "rectangle" and c[2] == (255, 222, 110, 255) for c in calls))
        self.assertIn("You made it!", self.strings(calls))


class CelebrationTimingTests(Base):
    def success_session(self):
        return lone_session(10000, 0, sync.SUCCESS, result_total=10000, result_added=100, previous_total=9900)

    def test_confetti_is_shorter_than_the_success_state(self):
        self.assertLess(sync_layout.CONFETTI_MS, sync.SUCCESS_MS)

    def test_confetti_fades_and_ends(self):
        alphas = [sync_layout.confetti_alpha(t) for t in range(0, sync_layout.CONFETTI_MS + 1, 50)]
        self.assertEqual(alphas[0], 1.0)
        self.assertEqual(alphas[-1], 0.0)
        self.assertEqual(alphas, sorted(alphas, reverse=True))
        self.assertEqual(sync_layout.confetti_alpha(sync.SUCCESS_MS), 0.0)
        self.assertEqual(sync_layout.confetti_alpha(-5), 0.0)

    def test_particles_are_deterministic_and_start_above_the_screen(self):
        a = sync_layout.confetti_particles(320)
        self.assertEqual(a, sync_layout.confetti_particles(320))
        self.assertEqual(len(a), sync_layout.CONFETTI_COUNT)
        for p in a:
            x, y = sync_layout.confetti_pose(p, 0)
            self.assertLess(y, 0)
            self.assertGreaterEqual(x, -20)
            self.assertLessEqual(x, 340)
            self.assertLess(p[5], len(sync_layout.CONFETTI_RGB))

    def test_confetti_moves_with_ticks_delta_and_ends(self):
        s = self.success_session()
        counts = []
        positions = []
        for _ in range(sync_layout.CONFETTI_MS // 100 + 3):
            calls = self.render(s)
            counts.append(len(self.confetti(calls)))
            positions.append([c[1] for c in self.confetti(calls)])
        self.assertGreater(counts[0], 0)
        self.assertNotEqual(positions[0], positions[1])  # advances with ticks_delta
        self.assertEqual(counts[-1], 0)  # and ends
        self.assertEqual(counts[-2], 0)
        # even if the app keeps drawing, nothing comes back
        self.assertEqual(len(self.confetti(self.render(s))), 0)

    def test_confetti_does_not_advance_when_ticks_delta_is_zero(self):
        s = self.success_session()
        self.render(s)
        self.badge.ticks_delta = 0
        first = [c[1] for c in self.confetti(self.render(s))]
        second = [c[1] for c in self.confetti(self.render(s))]
        self.assertTrue(first)
        self.assertEqual(first, second)

    def test_a_stalled_frame_does_not_skip_the_celebration(self):
        s = self.success_session()
        self.badge.ticks_delta = 5000
        self.assertGreater(len(self.confetti(self.render(s))), 0)

    def test_confetti_restarts_for_the_next_success(self):
        s = self.success_session()
        for _ in range(sync_layout.CONFETTI_MS // 100 + 2):
            self.render(s)
        self.assertEqual(len(self.confetti(self.render(s))), 0)
        s.state = sync.SEPARATE
        self.render(s)
        s.state = sync.WALKING
        self.render(s)
        s.state = sync.SUCCESS
        self.assertGreater(len(self.confetti(self.render(s))), 0)

    def test_real_session_celebration_ends_with_the_state_then_separate_prompt(self):
        p = Pair()
        settle_first_sync(p)
        p.la.add_steps(60)
        p.lb.add_steps(40)
        p.hold()
        confetti_by_state = {}
        for _ in range(80):
            p.step()
            calls = self.render(p.b)
            confetti_by_state.setdefault(p.b.state, []).append(len(self.confetti(calls)))
        self.assertTrue(all(n > 0 for n in confetti_by_state[sync.SUCCESS][:3]))
        self.assertEqual(confetti_by_state[sync.SUCCESS][-1], 0)
        self.assertTrue(all(n == 0 for n in confetti_by_state[sync.SEPARATE]))
        self.assertTrue(all(n == 0 for n in confetti_by_state[sync.HOLD]))


class ViewModelTests(unittest.TestCase):
    def test_separate_shows_pending_taken_during_the_exchange(self):
        s = lone_session(10000, 5, sync.SEPARATE, result_total=10000, result_added=100, previous_total=9900)
        vm = sync_layout.view_model(s)
        self.assertEqual(vm["total_text"], "10,000")
        self.assertEqual(vm["plus_text"], "+5")
        self.assertEqual(vm["title"], "Move badges apart")

    def test_walking_view_model_matches_the_main_screen(self):
        s = lone_session(9900, 60, sync.WALKING)
        vm = sync_layout.view_model(s)
        main = layout.view_model(s.ledger)
        self.assertEqual(vm["total_text"], main["big_text"])
        self.assertEqual(vm["plus_text"], main["plus_text"])
        self.assertEqual(vm["title"], main["status_text"])
        self.assertFalse(vm["celebrate"])

    def test_zero_added_first_sync_has_no_plus_together(self):
        s = lone_session(0, 0, sync.SUCCESS, result_total=0, result_added=0, previous_total=None)
        vm = sync_layout.view_model(s)
        self.assertEqual(vm["total_text"], "0")
        self.assertNotIn("together", vm["subtitle"])

    def test_retry_reason_texts(self):
        self.assertEqual(sync_layout.retry_reason_text(sync.REASON_DROPPED), "Badges moved apart too soon")
        self.assertEqual(sync_layout.retry_reason_text(sync.REASON_TIMEOUT), "Timed out")
        self.assertEqual(sync_layout.retry_reason_text(sync.REASON_MISMATCH), "Try again")


if __name__ == "__main__":
    unittest.main()
