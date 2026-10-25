import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "badge", "apps", "walking"))
from ledger import GOAL, Ledger  # noqa: E402


def seeded():
    """Martin 9,900 confirmed, Maggie 0, both synced."""
    m = Ledger("martin")
    m.add_steps(9900)
    g = Ledger("maggie")
    sm = m.receive(g.outgoing_contributions())
    sg = g.receive(m.outgoing_contributions())
    m.commit(sm)
    g.commit(sg)
    return m, g


class LedgerTests(unittest.TestCase):
    def test_goal(self):
        self.assertEqual(GOAL, 10000)

    def test_no_confirmed_total_before_sync_vs_zero(self):
        a = Ledger("martin")
        self.assertIsNone(a.confirmed_total)
        a.commit(a.receive({"maggie": 0}))
        self.assertEqual(a.confirmed_total, 0)
        self.assertIsNotNone(a.confirmed_total)

    def test_add_steps_only_changes_pending(self):
        m, _ = seeded()
        m.add_steps(25)
        self.assertEqual(m.pending, 25)
        self.assertEqual(m.confirmed_total, 9900)
        a = Ledger("x")
        a.add_steps(5)
        self.assertIsNone(a.confirmed_total)

    def test_merge_max_and_no_double_count(self):
        m, g = seeded()
        remote = {"martin": 9900, "maggie": 0}
        m.commit(m.receive(remote))
        m.commit(m.receive(remote))
        self.assertEqual(m.confirmed_total, 9900)
        s = m.receive({"maggie": 30})
        m.commit(s)
        m.commit(s)
        self.assertEqual(m.confirmed_total, 9930)
        m.commit(m.receive({"maggie": 30, "martin": 100}))
        self.assertEqual(m.confirmed_total, 9930)

    def test_discard_keeps_state(self):
        m, _ = seeded()
        m.add_steps(40)
        before = m.to_dict()
        s = m.receive({"maggie": 60, "martin": 9900})
        m.discard(s)
        m.commit(s)
        self.assertEqual(m.to_dict(), before)
        self.assertEqual(m.pending, 40)
        self.assertEqual(m.confirmed_total, 9900)

    def test_receive_does_not_mutate(self):
        m, _ = seeded()
        m.add_steps(40)
        before = m.to_dict()
        m.receive({"maggie": 60})
        self.assertEqual(m.to_dict(), before)

    def test_canonical_fixture_reaches_goal_on_ack(self):
        m, g = seeded()
        self.assertEqual(m.confirmed_total, 9900)
        self.assertEqual(g.confirmed_total, 9900)
        g.add_steps(60)
        m.add_steps(40)
        self.assertEqual(m.confirmed_total, 9900)
        self.assertEqual(g.confirmed_total, 9900)
        sm = m.receive(g.outgoing_contributions())
        sg = g.receive(m.outgoing_contributions())
        self.assertEqual(m.confirmed_total, 9900)
        m.commit(sm)
        g.commit(sg)
        for led in (m, g):
            self.assertEqual(led.confirmed_total, 10000)
            self.assertEqual(led.contributions, {"maggie": 60, "martin": 9940})
            self.assertEqual(led.pending, 0)
        self.assertEqual(m.partner, "maggie")
        self.assertEqual(g.partner, "martin")

    def test_steps_added_between_receive_and_commit_kept(self):
        m, _ = seeded()
        m.add_steps(40)
        s = m.receive({"maggie": 60})
        m.add_steps(7)
        m.commit(s)
        self.assertEqual(m.pending, 7)
        self.assertEqual(m.confirmed_total, 10000)
        self.assertEqual(m.outgoing_contributions()["martin"], 9947)

    def test_serialisation_round_trip(self):
        m, _ = seeded()
        m.add_steps(12)
        d = m.to_dict()
        d2 = json.loads(json.dumps(d))
        self.assertEqual(d2, d)
        r = Ledger.from_dict(d2)
        self.assertEqual(r.to_dict(), d)
        self.assertEqual(r.pending, 12)
        self.assertEqual(r.partner, "maggie")
        fresh = Ledger.from_dict(Ledger("a").to_dict())
        self.assertIsNone(fresh.confirmed_total)
        self.assertIsNone(fresh.partner)


if __name__ == "__main__":
    unittest.main()
