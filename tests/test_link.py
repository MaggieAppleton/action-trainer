import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "walk_together"))

import ledger  # noqa: E402
import link  # noqa: E402
import packet  # noqa: E402
import protocol  # noqa: E402

MAGGIE, MARTIN, STRANGER = 0xA1, 0xB2, 0xC3
GOALS = (("A", 100), ("B", 300))


class FakeRadio:
    def __init__(self):
        self.started = False
        self.adverts = []  # every advertise() call, in order
        self.inbox = []

    def start(self):
        self.started = True

    def stop(self):
        self.started = False

    def advertise(self, adv):
        self.adverts.append(adv)

    def poll(self):
        out, self.inbox = self.inbox, []
        return out

    def hear(self, adv, key="addr"):
        self.inbox.append((key, adv))


def deliver(src, dst):
    """The destination radio hears the source's current advertisement."""
    dst.hear(src.adverts[-1])


def make(badge_id, partner=0, own=0, **kw):
    led = ledger.Ledger(GOALS)
    led.add_steps(own)
    if partner:
        led.pair(partner)
    radio = FakeRadio()
    return link.Link(radio, led, badge_id, **kw), radio, led


class WalkTests(unittest.TestCase):
    def test_walk_apart_reconnect_twice_no_double_count(self):
        # Maggie 700 + Martin 500 = 1200 last shared.
        m, mr, ml = make(MAGGIE, partner=MARTIN, own=700)
        t, tr, tl = make(MARTIN, partner=MAGGIE, own=500)
        m.update(0)
        t.update(0)
        deliver(tr, mr)
        deliver(mr, tr)
        self.assertTrue(m.update(1000))
        self.assertTrue(t.update(1000))
        self.assertEqual(ml.pooled_total(), 1200)
        self.assertEqual(tl.pooled_total(), 1200)

        # Apart: both add steps; nothing crosses.
        ml.add_steps(300)
        tl.add_steps(450)
        m.update(5000)
        t.update(5000)
        self.assertEqual(ml.apart_view()["own_new_steps"], 300)
        self.assertEqual(ml.last_shared_total(), 1200)
        self.assertEqual(tl.pooled_total(), 1200 + 450)

        # Reconnect.
        deliver(tr, mr)
        deliver(mr, tr)
        m.update(20000)
        t.update(20000)
        self.assertEqual(ml.pooled_total(), 1950)
        self.assertEqual(tl.pooled_total(), 1950)

        # Reconnect again, repeated packets: unchanged and nothing to save.
        for now in (21000, 22000):
            deliver(tr, mr)
            deliver(mr, tr)
            deliver(tr, mr)
            self.assertFalse(m.update(now))
            self.assertFalse(t.update(now))
        self.assertEqual(ml.pooled_total(), 1950)
        self.assertEqual(tl.pooled_total(), 1950)

    def test_stale_packet_never_increases_pooled(self):
        m, mr, ml = make(MAGGIE, partner=MARTIN, own=10)
        mr.hear(packet.pack_adv(MARTIN, MAGGIE, 500, 2))
        self.assertTrue(m.update(0))
        mr.hear(packet.pack_adv(MARTIN, MAGGIE, 400, 1))
        mr.hear(packet.pack_adv(MARTIN, MAGGIE, 500, 3))
        self.assertFalse(m.update(100))
        self.assertEqual(ml.pooled_total(), 510)

    def test_foreign_and_non_walk_packets_ignored(self):
        m, mr, ml = make(MAGGIE, partner=MARTIN, own=10)
        mr.hear(packet.pack_adv(STRANGER, MAGGIE, 9999, 1))
        mr.hear(packet.pack_adv(MAGGIE, MARTIN, 9999, 1))  # our own echo
        airtime = protocol.adv_payload(protocol.pack_mfg(MARTIN, 1, 1, 0, 0, 0, 0, 0, 0, 5))
        mr.hear(airtime)
        mr.hear(b"\x02\x01\x06")
        mr.hear(b"")
        self.assertFalse(m.update(0))
        self.assertEqual(ml.pooled_total(), 10)
        self.assertFalse(m.in_range(0))

    def test_unpaired_badge_merges_nothing(self):
        m, mr, ml = make(MAGGIE, own=10)
        mr.hear(packet.pack_adv(MARTIN, 0, 500, 1))
        self.assertFalse(m.update(0))
        self.assertEqual(ml.pooled_total(), 10)


class RangeTests(unittest.TestCase):
    def test_out_of_range_after_timeout_and_back_on_next_packet(self):
        m, mr, _ = make(MAGGIE, partner=MARTIN, out_of_range_ms=5000)
        self.assertFalse(m.in_range(0))
        self.assertIsNone(m.view(0)["ms_since_exchange"])
        mr.hear(packet.pack_adv(MARTIN, MAGGIE, 5, 1))
        m.update(1000)
        self.assertTrue(m.in_range(1000))
        self.assertTrue(m.in_range(5999))
        self.assertFalse(m.in_range(6000))
        self.assertEqual(m.view(4000)["ms_since_exchange"], 3000)
        mr.hear(packet.pack_adv(MARTIN, MAGGIE, 5, 2))  # same total still proves presence
        m.update(9000)
        self.assertTrue(m.in_range(9000))

    def test_default_timeout_is_named_constant(self):
        m, _, _ = make(MAGGIE, partner=MARTIN)
        self.assertEqual(m.out_of_range_ms, link.OUT_OF_RANGE_MS)

    def test_foreign_packets_do_not_make_us_in_range(self):
        m, mr, _ = make(MAGGIE, partner=MARTIN)
        mr.hear(packet.pack_adv(STRANGER, MAGGIE, 5, 1))
        m.update(0)
        self.assertFalse(m.in_range(0))


class AdvertTests(unittest.TestCase):
    def test_refresh_only_when_own_total_changes(self):
        m, mr, ml = make(MAGGIE, partner=MARTIN, own=5)
        m.update(0)
        self.assertEqual(len(mr.adverts), 1)
        d = packet.unpack_mfg(link.mfg_from_adv(mr.adverts[0]))
        self.assertEqual((d["badge_id"], d["partner_id"], d["steps"]), (MAGGIE, MARTIN, 5))
        m.update(5000)
        m.update(9000)
        self.assertEqual(len(mr.adverts), 1)
        ml.add_steps(3)
        m.update(10000)
        self.assertEqual(len(mr.adverts), 2)
        d2 = packet.unpack_mfg(link.mfg_from_adv(mr.adverts[1]))
        self.assertEqual(d2["steps"], 8)
        self.assertNotEqual(d2["seq"], d["seq"])

    def test_refresh_is_throttled_but_not_lost(self):
        m, mr, ml = make(MAGGIE, partner=MARTIN, own=1)
        m.update(0)
        ml.add_steps(1)
        m.update(100)  # too soon
        self.assertEqual(len(mr.adverts), 1)
        m.update(link.ADVERT_MIN_MS)
        self.assertEqual(len(mr.adverts), 2)
        self.assertEqual(packet.unpack_mfg(link.mfg_from_adv(mr.adverts[1]))["steps"], 2)

    def test_start_and_stop_reach_radio(self):
        m, mr, _ = make(MAGGIE)
        m.start()
        self.assertTrue(mr.started)
        m.stop()
        self.assertFalse(mr.started)


class PairingTests(unittest.TestCase):
    def test_pair_select_and_persist_across_reboot(self):
        m, mr, ml = make(MAGGIE, own=40)
        m.start_pairing()
        mr.hear(packet.pack_adv(STRANGER, 0, 7, 1))
        mr.hear(packet.pack_adv(MARTIN, 0, 500, 1))
        mr.hear(packet.pack_adv(MARTIN, 0, 501, 2))  # duplicate listing collapsed
        mr.hear(packet.pack_adv(MAGGIE, 0, 40, 1))  # ourselves
        m.update(0)
        self.assertEqual(m.candidates, [STRANGER, MARTIN])
        self.assertEqual(m.selected_candidate(), STRANGER)
        self.assertEqual(m.next_candidate(), MARTIN)
        self.assertEqual(m.confirm(), MARTIN)
        self.assertFalse(m.pairing)
        self.assertEqual(ml.partner_id, MARTIN)

        # Reboot: restore ledger, new link. Partner kept, strangers ignored.
        saved = ml.to_dict()
        r2 = FakeRadio()
        m2 = link.Link(r2, ledger.Ledger.from_dict(saved, GOALS), MAGGIE)
        self.assertEqual(m2.ledger.partner_id, MARTIN)
        r2.hear(packet.pack_adv(STRANGER, MAGGIE, 999, 1))
        r2.hear(packet.pack_adv(MARTIN, MAGGIE, 500, 3))
        self.assertTrue(m2.update(0))
        self.assertEqual(m2.ledger.pooled_total(), 540)

    def test_confirm_advertises_new_partner_immediately(self):
        m, mr, _ = make(MAGGIE, own=1)
        m.update(0)
        m.start_pairing()
        mr.hear(packet.pack_adv(MARTIN, 0, 5, 1))
        m.update(10)
        m.confirm()
        m.update(20)  # well inside ADVERT_MIN_MS
        self.assertEqual(len(mr.adverts), 2)
        self.assertEqual(packet.unpack_mfg(link.mfg_from_adv(mr.adverts[1]))["partner_id"], MARTIN)

    def test_no_candidates_outside_pairing_mode_or_when_empty(self):
        m, mr, _ = make(MAGGIE)
        mr.hear(packet.pack_adv(MARTIN, 0, 5, 1))
        m.update(0)
        self.assertEqual(m.candidates, [])
        m.start_pairing()
        self.assertIsNone(m.confirm())
        self.assertIsNone(m.next_candidate())

    def test_cancel_pairing(self):
        m, _, _ = make(MAGGIE)
        m.start_pairing()
        m.cancel_pairing()
        self.assertFalse(m.pairing)
        self.assertFalse(m.view(0)["paired"])


class FakeBluetooth:
    """Stands in for the firmware `bluetooth` module."""

    class BLE:
        last = None

        def __init__(self):
            FakeBluetooth.BLE.last = self
            self.calls = []
            self.handler = None

        def active(self, on=None):
            self.calls.append(("active", on))

        def irq(self, handler):
            self.handler = handler

        def gap_scan(self, *args):
            self.calls.append(("gap_scan",) + args)

        def gap_advertise(self, interval, adv_data=None, connectable=True):
            self.calls.append(("gap_advertise", interval, adv_data, connectable))


class BleRadioTests(unittest.TestCase):
    def test_scan_results_queue_walk_packets_only_and_scan_restarts(self):
        radio = link.BleRadio(FakeBluetooth)
        radio.start()
        ble = FakeBluetooth.BLE.last
        self.assertIn(("active", True), ble.calls)
        scans = [c for c in ble.calls if c[0] == "gap_scan"]
        self.assertEqual(len(scans), 1)

        walk = packet.pack_adv(MARTIN, MAGGIE, 70000, 1)
        other = protocol.adv_payload(protocol.pack_mfg(MARTIN, 1, 1, 0, 0, 0, 0, 0, 0, 5))
        ble.handler(5, (0, memoryview(b"\x01\x02\x03\x04\x05\x06"), 3, -60, memoryview(walk)))
        ble.handler(5, (0, memoryview(b"\x01\x02\x03\x04\x05\x06"), 3, -60, memoryview(other)))
        got = radio.poll()
        self.assertEqual(got, [((0, b"\x01\x02\x03\x04\x05\x06"), walk)])
        self.assertEqual(radio.poll(), [])

        ble.handler(6, ())  # scan finished -> restarted on next poll
        radio.poll()
        self.assertEqual(len([c for c in ble.calls if c[0] == "gap_scan"]), 2)

    def test_queue_is_bounded(self):
        radio = link.BleRadio(FakeBluetooth)
        radio.start()
        walk = packet.pack_adv(MARTIN, MAGGIE, 1, 1)
        for _ in range(link.MAX_QUEUE + 10):
            FakeBluetooth.BLE.last.handler(5, (0, b"\x00" * 6, 3, -60, walk))
        self.assertEqual(len(radio.poll()), link.MAX_QUEUE)

    def test_advertise_is_non_connectable(self):
        radio = link.BleRadio(FakeBluetooth)
        radio.start()
        adv = packet.pack_adv(MAGGIE, 0, 1, 1)
        radio.advertise(adv)
        call = FakeBluetooth.BLE.last.calls[-1]
        self.assertEqual(call, ("gap_advertise", radio.ADV_INTERVAL_US, adv, False))
        radio.stop()
        self.assertIn(("active", False), FakeBluetooth.BLE.last.calls)


if __name__ == "__main__":
    unittest.main()
