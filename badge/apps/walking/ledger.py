"""Shared team-progress ledger for the two-person walking game.

Pure MicroPython-compatible logic: plain classes and dicts only.
"""

GOAL = 10000


class Exchange:
    """A received-but-unacknowledged proposal. Created by Ledger.receive()."""

    def __init__(self, merged, folded, partner):
        self.merged = merged
        self.folded = folded
        self.partner = partner
        self.done = False


class Ledger:
    def __init__(self, me):
        self.me = me
        self.contributions = {me: 0}  # confirmed per-person steps
        self.confirmed_total = None  # None until the first acknowledged sync
        self.partner = None
        self.pending = 0  # own unshared steps

    def add_steps(self, n):
        if n > 0:
            self.pending += n

    def outgoing_contributions(self):
        out = dict(self.contributions)
        out[self.me] = self.contributions.get(self.me, 0) + self.pending
        return out

    def receive(self, remote):
        """Stage a merge (per-person max) without changing confirmed state."""
        merged = self.outgoing_contributions()
        partner = None
        for pid in remote:
            if pid != self.me:
                partner = pid
            if remote[pid] > merged.get(pid, 0):
                merged[pid] = remote[pid]
        if partner is None:
            partner = self.partner
        return Exchange(merged, self.pending, partner)

    def commit(self, staged):
        """Apply a staged exchange once both badges acknowledged it."""
        if staged.done:
            return
        staged.done = True
        self.contributions = dict(staged.merged)
        self.contributions.setdefault(self.me, 0)
        self.pending = max(0, self.pending - staged.folded)
        self.partner = staged.partner
        self.confirmed_total = sum(self.contributions.values())

    def discard(self, staged):
        staged.done = True

    def to_dict(self):
        return {
            "me": self.me,
            "contributions": dict(self.contributions),
            "confirmed_total": self.confirmed_total,
            "partner": self.partner,
            "pending": self.pending,
        }

    @classmethod
    def from_dict(cls, d):
        led = cls(d["me"])
        led.contributions = dict(d.get("contributions") or {})
        led.contributions.setdefault(led.me, 0)
        led.confirmed_total = d.get("confirmed_total")
        led.partner = d.get("partner")
        led.pending = d.get("pending", 0)
        return led
