"""Pooled step ledger for Walk Together (plain MicroPython, hardware-free).

Each badge counts its own cumulative steps and learns the partner's latest
cumulative total. pooled = own + highest partner total received, so repeated
or stale packets never count a step twice. Time is passed in as `now` (ms).
"""

# Goal milestones along the walk: (name, pooled steps needed).
GOALS = (
    ("Meadow gate", 1000),
    ("Old oak", 2500),
    ("Windmill", 5000),
    ("River bridge", 8000),
    ("Hilltop", 12000),
)


class Ledger:
    def __init__(self, goals=GOALS):
        self.goals = goals
        self.own = 0
        self.partner_id = 0  # 0 = unpaired
        self.partner_total = 0
        self.last_exchange = None  # ms timestamp of last valid partner packet
        self.shared_own = 0  # own total when the last exchange happened

    def add_steps(self, n=1):
        if n > 0:
            self.own += n

    def pair(self, partner_id):
        """Pair with a partner; changing partner clears partner progress."""
        if partner_id != self.partner_id:
            self.partner_id = partner_id
            self.partner_total = 0
            self.last_exchange = None
            self.shared_own = self.own

    def receive(self, sender_id, total, now):
        """Merge a partner cumulative total. Returns True if pooled grew."""
        if not self.partner_id or sender_id != self.partner_id:
            return False
        before = self.pooled_total()
        if total > self.partner_total:
            self.partner_total = total
        self.last_exchange = now
        self.shared_own = self.own
        return self.pooled_total() > before

    def pooled_total(self):
        return self.own + self.partner_total

    def last_shared_total(self):
        """Pooled total as of the last exchange."""
        return self.shared_own + self.partner_total

    def own_new_steps(self):
        """Own steps counted since the last exchange."""
        return self.own - self.shared_own

    def apart_view(self):
        """What to show while no partner total has arrived since separating."""
        return {
            "last_shared_total": self.last_shared_total(),
            "own_new_steps": self.own_new_steps(),
            "last_exchange": self.last_exchange,
        }

    def goal_info(self):
        """Current goal, steps to the next goal and fractional progress 0..1.

        Progress is measured within the leg between the previous and next goal.
        After the last goal, goal is None and progress is 1.0.
        """
        total = self.pooled_total()
        prev = 0
        for i, (name, target) in enumerate(self.goals):
            if total < target:
                span = target - prev
                return {
                    "index": i,
                    "goal": name,
                    "target": target,
                    "steps_to_next": target - total,
                    "progress": (total - prev) / span,
                    "reached": i,
                }
            prev = target
        return {
            "index": len(self.goals),
            "goal": None,
            "target": prev,
            "steps_to_next": 0,
            "progress": 1.0,
            "reached": len(self.goals),
        }

    def to_dict(self):
        return {
            "own": self.own,
            "partner_id": self.partner_id,
            "partner_total": self.partner_total,
            "last_exchange": self.last_exchange,
            "shared_own": self.shared_own,
        }

    @classmethod
    def from_dict(cls, d, goals=GOALS):
        led = cls(goals)
        led.own = d.get("own", 0)
        led.partner_id = d.get("partner_id", 0)
        led.partner_total = d.get("partner_total", 0)
        led.last_exchange = d.get("last_exchange")
        led.shared_own = d.get("shared_own", 0)
        return led
