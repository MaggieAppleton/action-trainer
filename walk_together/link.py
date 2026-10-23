"""Bluetooth LE link for Walk Together (plain MicroPython).

`Link` advertises this badge's cumulative total (packet.py), feeds the paired
partner's advertisements into the ledger's idempotent merge, and reports
In range / Out of range. It talks to the radio only through a small adapter,
so the logic runs on the desktop with a fake radio.

Radio adapter interface (see `BleRadio` for the firmware implementation):

    start()            power up and begin scanning
    stop()             power down
    advertise(adv)     replace the advertisement with these bytes; non-blocking
    poll() -> list     (key, adv_bytes) tuples received since the last call

Time is passed in as `now` (a non-wrapping millisecond clock chosen by the
app), the same clock given to `Ledger.receive`. Nothing here blocks.

No range in metres is implied: "In range" simply means a valid packet from
the paired partner arrived within OUT_OF_RANGE_MS.
"""

import packet

# No partner packet for this long -> Out of range.
OUT_OF_RANGE_MS = 10000
# Re-advertise at most this often when own steps change (steps tick often).
ADVERT_MIN_MS = 1000
# Pairing list size and radio receive queue bound.
MAX_CANDIDATES = 8
MAX_QUEUE = 16


def mfg_from_adv(adv):
    """Manufacturer data (with company ID) from an advertisement, or None."""
    offset = 0
    while offset < len(adv):
        length = adv[offset]
        if not length or offset + length >= len(adv):
            return None
        if adv[offset + 1] == 0xFF:
            return bytes(adv[offset + 2 : offset + length + 1])
        offset += length + 1
    return None


class Link:
    def __init__(self, radio, ledger, badge_id, out_of_range_ms=OUT_OF_RANGE_MS):
        self.radio = radio
        self.ledger = ledger
        self.badge_id = badge_id
        self.out_of_range_ms = out_of_range_ms
        self._seq = 0
        self._advertised = None  # (own, partner_id) last put on air
        self._adv_at = None
        self._last_seen = None  # this session only; never persisted
        self._pairing = False
        self.candidates = []  # badge ids heard while pairing
        self.selected = 0

    def start(self):
        self.radio.start()

    def stop(self):
        self.radio.stop()

    # -- walking -----------------------------------------------------------

    def update(self, now):
        """Process received packets and refresh the advertisement if needed.

        Returns True when the pooled total grew (the app should save state).
        """
        grew = False
        for _key, adv in self.radio.poll():
            mfg = mfg_from_adv(adv)
            d = packet.unpack_mfg(mfg) if mfg else None
            if d is None or d["badge_id"] == self.badge_id:
                continue
            sender = d["badge_id"]
            if self._pairing:
                self._note_candidate(sender)
            if self.ledger.partner_id and sender == self.ledger.partner_id:
                self._last_seen = now
                if self.ledger.receive(sender, d["steps"], now):
                    grew = True
        self._refresh_advert(now)
        return grew

    def in_range(self, now):
        return self._last_seen is not None and now - self._last_seen < self.out_of_range_ms

    def view(self, now):
        """Link facts for the screen's view-model."""
        since = None if self._last_seen is None else now - self._last_seen
        return {
            "in_range": self.in_range(now),
            "ms_since_exchange": since,
            "paired": bool(self.ledger.partner_id),
            "pairing": self._pairing,
        }

    def _refresh_advert(self, now):
        key = (self.ledger.own, self.ledger.partner_id)
        if key == self._advertised:
            return
        if self._adv_at is not None and now - self._adv_at < ADVERT_MIN_MS:
            return
        self._seq = (self._seq + 1) & 0xFFFF
        self.radio.advertise(packet.pack_adv(self.badge_id, self.ledger.partner_id, self.ledger.own, self._seq))
        self._advertised = key
        self._adv_at = now

    # -- pairing -----------------------------------------------------------

    def start_pairing(self):
        self._pairing = True
        self.candidates = []
        self.selected = 0

    def cancel_pairing(self):
        self._pairing = False

    @property
    def pairing(self):
        return self._pairing

    def _note_candidate(self, badge_id):
        if badge_id not in self.candidates and len(self.candidates) < MAX_CANDIDATES:
            self.candidates.append(badge_id)

    def selected_candidate(self):
        if self.candidates:
            return self.candidates[self.selected % len(self.candidates)]
        return None

    def next_candidate(self):
        """Move the highlight to the next nearby badge (e.g. BUTTON_DOWN)."""
        if self.candidates:
            self.selected = (self.selected + 1) % len(self.candidates)
        return self.selected_candidate()

    def confirm(self):
        """Pair with the highlighted badge (e.g. BUTTON_SELECT).

        Returns the partner id, or None if nothing is highlighted. The app
        should then save `ledger.to_dict()` so the partner survives a reboot.
        """
        partner = self.selected_candidate()
        if partner is None:
            return None
        self.ledger.pair(partner)
        self._pairing = False
        self._last_seen = None
        self._adv_at = None  # advertise the new partner id straight away
        return partner


class BleRadio:
    """Radio adapter over the firmware `bluetooth` module.

    Modelled on badge/apps/camera/camera_ble.py in badger/home (BLE() setup,
    irq(), gap_scan(), event 5 scan results). Not exercised on hardware.
    """

    _IRQ_SCAN_RESULT = 5
    _IRQ_SCAN_DONE = 6
    ADV_INTERVAL_US = 200000
    SCAN_INTERVAL_US = 100000
    SCAN_WINDOW_US = 30000

    def __init__(self, bluetooth_module=None):
        if bluetooth_module is None:
            import bluetooth as bluetooth_module
        self._bt = bluetooth_module
        self._ble = None
        self._queue = []
        self._rescan = False

    def start(self):
        self._ble = self._bt.BLE()
        self._ble.active(True)
        self._ble.irq(self._irq)
        self._scan()

    def stop(self):
        if self._ble is not None:
            self._ble.irq(None)
            self._ble.active(False)
            self._ble = None

    def advertise(self, adv):
        self._ble.gap_advertise(self.ADV_INTERVAL_US, adv_data=adv, connectable=False)

    def poll(self):
        if self._rescan and self._ble is not None:
            self._rescan = False
            self._scan()
        out = self._queue
        self._queue = []
        return out

    def _scan(self):
        # duration 0 scans until stopped; passive is enough for adv data.
        self._ble.gap_scan(0, self.SCAN_INTERVAL_US, self.SCAN_WINDOW_US, False)

    def _irq(self, event, data):
        if event == self._IRQ_SCAN_RESULT:
            addr_type, addr, _adv_type, _rssi, adv = data
            adv = bytes(adv)
            if packet.MAGIC in adv and len(self._queue) < MAX_QUEUE:
                self._queue.append(((addr_type, bytes(addr)), adv))
        elif event == self._IRQ_SCAN_DONE:
            self._rescan = True
