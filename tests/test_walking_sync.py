import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "badge", "apps", "walking"))
import sync  # noqa: E402
from ledger import Ledger  # noqa: E402
from sync import (  # noqa: E402
    AWAITING_ACK,
    CONNECTING,
    EXCHANGE,
    HOLD,
    RETRY,
    SEPARATE,
    SUCCESS,
    UP_TO_DATE,
    WALKING,
    PacketError,
    Session,
)

STEP_MS = 100
BEFORE_SUCCESS = (HOLD, CONNECTING, EXCHANGE, AWAITING_ACK, RETRY)


class FakeLink:
    """Two linked fake transports. Up/down, severing and packet loss."""

    def __init__(self):
        self.up = False
        self.queues = {"a": [], "b": []}  # packets waiting to be received by side
        self.drop = None  # optional fn(sender, data) -> True to lose the packet
        self.a = FakeTransport(self, "a")
        self.b = FakeTransport(self, "b")

    def connect(self):
        self.up = True

    def sever(self):
        self.up = False
        self.queues = {"a": [], "b": []}


class FakeTransport:
    def __init__(self, link, side):
        self.link = link
        self.side = side
        self.sent = []

    def connected(self):
        return self.link.up

    def send(self, data):
        self.sent.append(data)
        if not self.link.up:
            return
        if self.link.drop is not None and self.link.drop(self.side, data):
            return
        self.link.queues["b" if self.side == "a" else "a"].append(data)

    def receive(self):
        q = self.link.queues[self.side]
        return q.pop(0) if q else None


class Pair:
    def __init__(self, a_id="maggie", b_id="martin"):
        self.link = FakeLink()
        self.la = Ledger(a_id)
        self.lb = Ledger(b_id)
        self.a = Session(self.la, self.link.a)
        self.b = Session(self.lb, self.link.b)
        self.trace_a = []
        self.trace_b = []

    def step(self, ms=STEP_MS):
        self.a.tick(ms)
        self.b.tick(ms)
        self.trace_a.append(self.a.state)
        self.trace_b.append(self.b.state)

    def run(self, ms, check=None):
        for _ in range(ms // STEP_MS):
            self.step()
            if check:
                check()

    def hold(self):
        self.link.connect()
        self.a.begin_hold()
        self.b.begin_hold()

    def sync(self, ms=20000):
        """Hold, then run until both sessions have left their active states."""
        self.hold()
        self.run(ms)

    def separate(self):
        self.link.sever()
        self.run(1000)


def dedupe(trace):
    out = []
    for s in trace:
        if not out or out[-1] != s:
            out.append(s)
    return out


class PacketTests(unittest.TestCase):
    def test_contributions_round_trip(self):
        data = {"martin": 9940, "maggie": 60}
        kind, payload = sync.unpack(sync.pack_contributions(data))
        self.assertEqual(kind, sync.TYPE_CONTRIBUTIONS)
        self.assertEqual(payload, data)

    def test_contributions_wire_layout(self):
        raw = sync.pack_contributions({"ab": 258})
        self.assertEqual(raw, b"WS\x01\x01" + b"\x01" + b"\x02ab" + b"\x02\x01\x00\x00")

    def test_extremes_round_trip(self):
        data = {"x": 0, "y" * sync.MAX_ID: sync.MAX_STEPS, "é": 5}
        self.assertEqual(sync.unpack(sync.pack_contributions(data))[1], data)

    def test_ack_round_trip_and_layout(self):
        raw = sync.pack_ack(10000)
        self.assertEqual(raw, b"WS\x01\x02" + struct.pack("<I", 10000))
        self.assertEqual(sync.unpack(raw), (sync.TYPE_ACK, 10000))

    def test_rejects_foreign_and_malformed(self):
        good = sync.pack_contributions({"maggie": 1, "martin": 2})
        ack = sync.pack_ack(3)
        bad = [
            None,
            b"",
            b"WS",
            b"AT\x01\x01" + good[4:],  # foreign magic (airtime advert uses AT)
            b"\x02\x01\x06" + b"\xff" * 20,  # a BLE advertisement
            good[:2] + b"\x02" + good[3:],  # wrong version
            good[:3] + b"\x09" + good[4:],  # unknown type
            good[:-1],  # truncated
            good + b"\x00",  # trailing byte
            ack[:-1],
            ack + b"\x00",
            good[:4] + b"\x00",  # zero people
            good[:4] + b"\x09" + good[5:],  # too many people declared
            b"WS\x01\x01\x01\x00\x01\x00\x00\x00",  # empty id
            b"WS\x01\x01\x02\x01a\x01\x00\x00\x00\x01a\x02\x00\x00\x00",  # duplicate id
            b"WS\x01\x01\x01\x02\xff\xfe\x01\x00\x00\x00",  # invalid UTF-8
            b"WS\x01\x01\x01\x11" + b"a" * 17 + b"\x01\x00\x00\x00",  # id too long
        ]
        for data in bad:
            with self.assertRaises(PacketError, msg=repr(data)):
                sync.unpack(data)

    def test_pack_rejects_out_of_range(self):
        with self.assertRaises(PacketError):
            sync.pack_contributions({})
        with self.assertRaises(PacketError):
            sync.pack_contributions({"": 1})
        with self.assertRaises(PacketError):
            sync.pack_contributions({"a" * 17: 1})
        with self.assertRaises(PacketError):
            sync.pack_contributions({"a": -1})
        with self.assertRaises(PacketError):
            sync.pack_contributions({"a": 2**32})
        with self.assertRaises(PacketError):
            sync.pack_contributions({str(i): 0 for i in range(9)})
        with self.assertRaises(PacketError):
            sync.pack_ack(2**32)


class SessionFlowTests(unittest.TestCase):
    def test_happy_path_states_in_order_for_both_badges(self):
        p = Pair()
        p.sync(8000)
        want = [WALKING, HOLD, CONNECTING, EXCHANGE, AWAITING_ACK, SUCCESS, SEPARATE]
        for trace in (p.trace_a, p.trace_b):
            seen = dedupe(trace)
            self.assertEqual(seen[: len(want) - 1], want[1:])  # begin_hold ran before tick 1
        # nothing leaves SEPARATE while the badges are still held together
        self.assertEqual(p.a.state, SEPARATE)
        self.assertEqual(p.b.state, SEPARATE)
        p.separate()
        self.assertEqual(p.a.state, WALKING)
        self.assertEqual(p.b.state, WALKING)

    def test_first_sync_with_no_steps_confirms_zero(self):
        p = Pair()
        self.assertIsNone(p.la.confirmed_total)
        p.sync(8000)
        self.assertEqual(p.la.confirmed_total, 0)
        self.assertEqual(p.lb.confirmed_total, 0)
        self.assertEqual(p.la.partner, "martin")
        self.assertEqual(p.lb.partner, "maggie")

    def test_canonical_fixture_reaches_goal(self):
        p = Pair()
        p.lb.add_steps(9900)
        p.sync(8000)
        p.separate()
        self.assertEqual((p.la.confirmed_total, p.lb.confirmed_total), (9900, 9900))
        self.assertEqual(p.a.result_added, 9900)
        self.assertIsNone(p.a.previous_total)

        p.la.add_steps(60)
        p.lb.add_steps(40)
        p.sync(8000)
        for s, led in ((p.a, p.la), (p.b, p.lb)):
            self.assertEqual(led.confirmed_total, 10000)
            self.assertEqual(led.contributions, {"maggie": 60, "martin": 9940})
            self.assertEqual(led.pending, 0)
            self.assertEqual(s.result_total, 10000)
            self.assertEqual(s.result_added, 100)
            self.assertEqual(s.previous_total, 9900)

    def test_confirmed_total_changes_only_on_entering_success(self):
        p = Pair()
        p.lb.add_steps(9900)
        p.sync(8000)
        p.separate()
        p.la.add_steps(60)
        p.lb.add_steps(40)
        before = {"a": p.la.to_dict(), "b": p.lb.to_dict()}
        seen = {"a": [], "b": []}

        def check():
            for key, s, led in (("a", p.a, p.la), ("b", p.b, p.lb)):
                seen[key].append((s.state, led.confirmed_total))
                if s.state in BEFORE_SUCCESS:
                    self.assertEqual(led.confirmed_total, 9900, s.state)
                    self.assertEqual(led.to_dict(), before[key], s.state)

        p.hold()
        p.run(8000, check)
        for key in ("a", "b"):
            totals = [t for st, t in seen[key] if st == SUCCESS]
            self.assertTrue(totals and all(t == 10000 for t in totals))
            self.assertEqual(seen[key][-1], (SEPARATE, 10000))

    def test_steps_counted_during_the_exchange_stay_pending(self):
        p = Pair()
        p.la.add_steps(10)
        p.lb.add_steps(20)
        p.hold()
        for _ in range(30):
            p.step()
            if p.a.state == EXCHANGE:
                p.la.add_steps(5)
                p.lb.add_steps(7)
        p.run(5000)
        self.assertEqual(p.a.state, SEPARATE)
        self.assertEqual(p.la.confirmed_total, 30)
        self.assertEqual(p.lb.confirmed_total, 30)
        self.assertEqual((p.la.pending, p.lb.pending), (5, 7))

    def test_begin_hold_only_from_walking_or_retry(self):
        p = Pair()
        p.hold()
        self.assertFalse(p.a.begin_hold())
        p.run(2000)
        self.assertFalse(p.a.begin_hold())

    def test_cancel_during_hold_returns_to_walking(self):
        p = Pair()
        p.a.begin_hold()
        p.a.tick(300)
        p.a.cancel()
        self.assertEqual(p.a.state, WALKING)
        self.assertIsNone(p.la.confirmed_total)


class RepeatAndUpToDateTests(unittest.TestCase):
    def test_repeat_exchange_with_nothing_new_is_up_to_date(self):
        p = Pair()
        p.la.add_steps(60)
        p.lb.add_steps(40)
        p.sync(8000)
        p.separate()
        before = (p.la.to_dict(), p.lb.to_dict())
        self.assertEqual(p.la.confirmed_total, 100)

        p.hold()
        p.run(2500)
        self.assertEqual(p.a.state, UP_TO_DATE)
        self.assertEqual(p.b.state, UP_TO_DATE)
        self.assertEqual((p.la.to_dict(), p.lb.to_dict()), before)
        self.assertEqual(p.a.result_total, 100)
        self.assertEqual(p.a.result_added, 0)
        p.run(3000)
        self.assertEqual((p.a.state, p.b.state), (SEPARATE, SEPARATE))
        p.separate()
        self.assertEqual((p.a.state, p.b.state), (WALKING, WALKING))
        self.assertEqual((p.la.to_dict(), p.lb.to_dict()), before)
        # UP_TO_DATE is never passed through SUCCESS
        self.assertNotIn(SUCCESS, p.trace_a[-60:])

    def test_up_to_date_keeps_pending_steps(self):
        p = Pair()
        p.sync(8000)
        p.separate()
        p.la.add_steps(5)  # only Maggie has something new
        p.hold()
        p.run(8000)
        # Maggie has news so she succeeds; Martin learns it as well
        self.assertEqual((p.la.confirmed_total, p.lb.confirmed_total), (5, 5))


class FailureTests(unittest.TestCase):
    def setUp(self):
        self.p = Pair()
        self.p.lb.add_steps(9900)
        self.p.sync(8000)
        self.p.separate()
        self.p.la.add_steps(60)
        self.p.lb.add_steps(40)

    def assert_safe(self, p):
        """Each badge is either fully committed or fully untouched."""
        for led, pending in ((p.la, 60), (p.lb, 40)):
            if led.confirmed_total == 9900:
                self.assertEqual(led.pending, pending)
            else:
                self.assertEqual(led.confirmed_total, 10000)
                self.assertEqual(led.pending, 0)

    def converge(self, p):
        p.link.sever()
        p.run(10000)
        p.sync(8000)
        self.assertEqual(p.la.confirmed_total, 10000)
        self.assertEqual(p.lb.confirmed_total, 10000)
        self.assertEqual(p.la.contributions, {"maggie": 60, "martin": 9940})
        self.assertEqual(p.lb.contributions, {"maggie": 60, "martin": 9940})
        self.assertEqual((p.la.pending, p.lb.pending), (0, 0))

    def test_drop_at_every_step_is_retry_safe(self):
        for n in range(1, 25):
            p = Pair()
            p.lb.add_steps(9900)
            p.sync(8000)
            p.separate()
            p.la.add_steps(60)
            p.lb.add_steps(40)
            p.hold()
            for _ in range(n):
                p.step()
            p.link.sever()
            p.run(8000)
            self.assert_safe(p)
            for s, led in ((p.a, p.la), (p.b, p.lb)):
                if led.confirmed_total == 9900:
                    self.assertEqual(s.state, RETRY, "n=%d" % n)
            self.converge(p)

    def test_timeout_when_peer_never_answers(self):
        p = self.p
        p.link.connect()
        p.a.begin_hold()  # Martin's badge never joins
        p.run(sync.HOLD_MS + 300)
        self.assertEqual(p.a.state, EXCHANGE)
        p.run(sync.EXCHANGE_TIMEOUT_MS)
        self.assertEqual(p.a.state, RETRY)
        self.assertEqual(p.a.retry_reason, sync.REASON_TIMEOUT)
        self.assertEqual(p.la.confirmed_total, 9900)
        self.assertEqual(p.la.pending, 60)

    def test_timeout_when_link_never_comes_up(self):
        p = self.p
        p.a.begin_hold()
        p.run(sync.HOLD_MS + sync.CONNECT_TIMEOUT_MS + 300)
        self.assertEqual(p.a.state, RETRY)
        self.assertEqual(p.a.retry_reason, sync.REASON_TIMEOUT)
        self.assertEqual(p.la.confirmed_total, 9900)

    def test_dropped_link_reports_reason_and_retry_recovers(self):
        p = self.p
        p.hold()
        while p.a.state != AWAITING_ACK:
            p.step()
        p.link.sever()
        p.run(500)
        self.assertEqual(p.a.state, RETRY)
        self.assertEqual(p.a.retry_reason, sync.REASON_DROPPED)
        self.assertEqual((p.la.confirmed_total, p.la.pending), (9900, 60))
        self.assertEqual((p.lb.confirmed_total, p.lb.pending), (9900, 40))
        p.link.connect()
        self.assertTrue(p.a.begin_hold() and p.b.begin_hold())
        p.run(8000)
        self.assertEqual((p.la.confirmed_total, p.lb.confirmed_total), (10000, 10000))

    def test_lost_ack_leaves_one_badge_stale_and_a_later_sync_heals_it(self):
        p = self.p
        # Martin's ack never reaches Maggie, Maggie's reaches Martin.
        p.link.drop = lambda side, data: side == "b" and sync.unpack(data)[0] == sync.TYPE_ACK
        p.hold()
        p.run(8000)
        # Martin got Maggie's ack and committed; Maggie timed out and kept her old state.
        self.assertEqual(p.lb.confirmed_total, 10000)
        self.assertEqual(p.la.confirmed_total, 9900)
        self.assertEqual((p.la.pending, p.a.state, p.a.retry_reason), (60, RETRY, sync.REASON_TIMEOUT))
        p.link.drop = None
        p.link.sever()
        p.run(1000)
        p.link.connect()
        p.a.begin_hold()
        p.b.begin_hold()
        p.run(8000)
        self.assertEqual(p.la.confirmed_total, 10000)
        self.assertEqual(p.lb.confirmed_total, 10000)
        self.assertEqual(p.la.contributions, p.lb.contributions)
        self.assertEqual(p.la.pending, 0)
        self.assertEqual(p.b.result_total, 10000)

    def test_wrong_ack_total_is_a_mismatch_retry(self):
        p = self.p
        p.link.connect()
        p.a.begin_hold()
        p.run(sync.HOLD_MS + 300)
        self.assertEqual(p.a.state, EXCHANGE)
        p.link.queues["a"].append(sync.pack_contributions({"martin": 9940}))
        p.link.queues["a"].append(sync.pack_ack(1))
        p.run(500)
        self.assertEqual(p.a.state, RETRY)
        self.assertEqual(p.a.retry_reason, sync.REASON_MISMATCH)
        self.assertEqual((p.la.confirmed_total, p.la.pending), (9900, 60))

    def test_junk_packets_are_ignored(self):
        p = self.p
        p.hold()
        while p.a.state != EXCHANGE:
            p.step()
        p.link.queues["a"].insert(0, b"garbage")
        p.link.queues["b"].insert(0, b"WS\x02\x01")
        p.run(8000)
        self.assertEqual(p.a.rejected, 1)
        self.assertEqual(p.b.rejected, 1)
        self.assertEqual((p.la.confirmed_total, p.lb.confirmed_total), (10000, 10000))

    def test_send_failure_moves_to_retry(self):
        p = self.p

        def boom(data):
            raise OSError("link lost")

        p.link.a.send = boom
        p.hold()
        p.run(sync.HOLD_MS + 500)
        self.assertEqual(p.a.state, RETRY)
        self.assertEqual(p.a.retry_reason, sync.REASON_SEND_FAILED)
        self.assertEqual((p.la.confirmed_total, p.la.pending), (9900, 60))

    def test_cancel_mid_exchange_goes_to_retry_then_walking(self):
        p = self.p
        p.hold()
        while p.a.state != EXCHANGE:
            p.step()
        p.a.cancel()
        self.assertEqual((p.a.state, p.a.retry_reason), (RETRY, sync.REASON_CANCELLED))
        self.assertEqual((p.la.confirmed_total, p.la.pending), (9900, 60))
        p.a.cancel()
        self.assertEqual(p.a.state, WALKING)

    def test_stale_packets_from_an_old_attempt_do_not_leak_into_the_next(self):
        p = self.p
        p.link.connect()
        p.link.queues["a"].append(sync.pack_contributions({"martin": 1}))
        p.link.queues["a"].append(sync.pack_ack(1))
        p.a.begin_hold()
        p.b.begin_hold()
        p.run(8000)
        self.assertEqual((p.la.confirmed_total, p.lb.confirmed_total), (10000, 10000))


if __name__ == "__main__":
    unittest.main()
