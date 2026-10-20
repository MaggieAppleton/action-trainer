"""Live console listener for air-time badges (advertising only, no pairing).

Usage:  python listen.py [--raw]
"""
import argparse
import asyncio
import time

from bleak import BleakScanner

from protocol import COMPANY_ID, unpack_mfg

STATE_NAMES = ("STILL", "WALK", "FLYING", "THROW", "DROP", "HANDLING")


class BadgeView:
    def __init__(self, address):
        self.address = address
        self.name = None
        self.rssi = None
        self.last = None
        self.boot = None
        self.seen = 0.0
        self.updates = 0

    def apply(self, d, name, rssi):
        events = []
        prev = self.last
        if prev is not None and prev["boot"] == d["boot"]:
            for key in ("throws", "drops"):
                n = (d[key] - prev[key]) & 0xFF
                if n:
                    events.append(f"{key[:-1]} x{n}" if n > 1 else key[:-1])
            if d["air_at_reset_ms"] != prev["air_at_reset_ms"]:
                events.append("still reset")
        elif prev is not None:
            events.append("rebooted")
        if prev is None or prev["seq"] != d["seq"]:
            self.updates += 1
        self.last = d
        self.name = name or self.name
        self.rssi = rssi
        self.seen = time.time()
        return events


def fmt_row(v):
    d = v.last
    state = STATE_NAMES[d["state"]] if d["state"] < len(STATE_NAMES) else str(d["state"])
    streak = (d["air_total_ms"] - d["air_at_reset_ms"]) / 1000
    age = time.time() - v.seen
    return (
        f"{(v.name or v.address)[:10]:<10} {state:<8} air {streak:5.2f}s tot {d['air_total_ms'] / 1000:6.2f}s "
        f"fl {d['flight_ms']:4d}ms T{d['throws']:<3d} D{d['drops']:<3d} st {d['steps']:<4d} {v.rssi}dB {age:3.1f}s"
    )


async def main(raw, seconds=None):
    badges = {}

    def on_adv(dev, adv):
        body = adv.manufacturer_data.get(COMPANY_ID)
        if body is None:
            return
        d = unpack_mfg(COMPANY_ID.to_bytes(2, "little") + bytes(body))
        if d is None:
            return
        v = badges.setdefault(dev.address, BadgeView(dev.address))
        events = v.apply(d, adv.local_name, adv.rssi)
        if raw:
            print(d)
        for e in events:
            print(f"\n*** {v.name or v.address}: {e.upper()}  (flight {d['flight_ms']} ms)")

    async with BleakScanner(on_adv, scanning_mode="active"):
        print("Listening for air-time badges... Ctrl+C to stop")
        end = time.time() + seconds if seconds else None
        while end is None or time.time() < end:
            await asyncio.sleep(0.25)
            if badges and not raw:
                rows = " | ".join(fmt_row(v) for v in badges.values())
                print("\r" + rows[:88].ljust(88), end="", flush=True)
    for v in badges.values():
        print(f"\n{v.name or v.address}: {v.updates} updates; final {fmt_row(v)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", action="store_true", help="print every decoded advert")
    ap.add_argument("--seconds", type=float, help="stop after this many seconds")
    args = ap.parse_args()
    try:
        asyncio.run(main(args.raw, args.seconds))
    except KeyboardInterrupt:
        pass
