import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "walk_together"))

import ledger  # noqa: E402

MAGGIE, MARTIN = 0xA1, 0xB2
GOALS = (("A", 100), ("B", 300))


def pair_at_1200():
    """Maggie 700 + Martin 500 = 1200 last shared."""
    m = ledger.Ledger(GOALS)
    m.add_steps(700)
    m.pair(MARTIN)
    m.receive(MARTIN, 500, 1000)
    return m


class PooledTests(unittest.TestCase):
    def test_pooled_is_own_plus_highest_partner(self):
        m = pair_at_1200()
        self.assertEqual(m.pooled_total(), 1200)
        self.assertFalse(m.receive(MARTIN, 500, 2000))
        self.assertFalse(m.receive(MARTIN, 400, 3000))
        self.assertEqual(m.pooled_total(), 1200)
        self.assertTrue(m.receive(MARTIN, 600, 4000))
        self.assertEqual(m.pooled_total(), 1300)

    def test_synthetic_walk_apart_and_reconnect(self):
        m = pair_at_1200()
        t = ledger.Ledger(GOALS)
        t.add_steps(500)
        t.pair(MAGGIE)
        t.receive(MAGGIE, 700, 1000)
        self.assertEqual(t.pooled_total(), 1200)
        m.add_steps(300)
        t.add_steps(450)
        # Apart: each shows last shared plus own new steps.
        self.assertEqual(m.apart_view(), {"last_shared_total": 1200, "own_new_steps": 300, "last_exchange": 1000})
        self.assertEqual(t.apart_view()["own_new_steps"], 450)
        self.assertEqual(m.pooled_total(), 1500)
        # Reconnect.
        m.receive(MARTIN, t.own, 9000)
        t.receive(MAGGIE, m.own, 9000)
        self.assertEqual(m.pooled_total(), 1950)
        self.assertEqual(t.pooled_total(), 1950)
        # Reconnect again: unchanged.
        m.receive(MARTIN, t.own, 9500)
        t.receive(MAGGIE, m.own, 9500)
        self.assertEqual(m.pooled_total(), 1950)
        self.assertEqual(t.pooled_total(), 1950)
        self.assertEqual(m.apart_view()["own_new_steps"], 0)
        self.assertEqual(m.last_exchange, 9500)

    def test_other_badge_ignored(self):
        m = pair_at_1200()
        self.assertFalse(m.receive(0xC3, 99999, 5000))
        self.assertEqual(m.pooled_total(), 1200)
        self.assertEqual(m.last_exchange, 1000)

    def test_unpaired_ignores_everything(self):
        m = ledger.Ledger(GOALS)
        self.assertFalse(m.receive(MARTIN, 50, 1))
        self.assertEqual(m.pooled_total(), 0)

    def test_roundtrip_dict(self):
        m = pair_at_1200()
        m.add_steps(7)
        d = m.to_dict()
        for v in d.values():
            self.assertIn(type(v), (int, type(None)))
        r = ledger.Ledger.from_dict(d, GOALS)
        self.assertEqual(r.to_dict(), d)
        self.assertEqual(r.pooled_total(), 1207)
        self.assertEqual(r.own_new_steps(), 7)
        self.assertEqual(ledger.Ledger.from_dict({}).pooled_total(), 0)

    def test_goals(self):
        m = ledger.Ledger(GOALS)
        g = m.goal_info()
        self.assertEqual((g["goal"], g["steps_to_next"], g["progress"]), ("A", 100, 0.0))
        m.add_steps(50)
        self.assertEqual(m.goal_info()["progress"], 0.5)
        m.add_steps(50)  # exactly at A: now heading to B
        g = m.goal_info()
        self.assertEqual((g["goal"], g["steps_to_next"], g["progress"], g["reached"]), ("B", 200, 0.0, 1))
        m.add_steps(500)
        g = m.goal_info()
        self.assertIsNone(g["goal"])
        self.assertEqual(g["progress"], 1.0)

    def test_default_goals_increasing(self):
        targets = [t for _, t in ledger.GOALS]
        self.assertEqual(targets, sorted(set(targets)))


if __name__ == "__main__":
    unittest.main()
