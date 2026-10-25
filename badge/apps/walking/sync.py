"""Walking sync: transport-independent packets and the session state machine.

Pure MicroPython-compatible logic (struct, plain classes, string constants).
No badge globals and no clock: the caller passes elapsed milliseconds to
``Session.tick`` (use ``badge.ticks_delta`` on the badge), and the transport is
any object with:

    connected() -> bool        # is the link to the other badge up right now?
    send(data: bytes)          # may raise OSError; the packet is then lost
    receive() -> bytes | None  # next whole packet, or None when empty

Which link provides that (BLE, IR, ...) is chosen separately.

Wire format (little endian), in the style of ``protocol.py``:

    header          "<2sBB"   magic b"WS", version, packet type
    contributions   header, count u8, then per person: id length u8,
                    id (UTF-8), steps u32
    acknowledgement header, merged team total u32

Limits: 1 to ``MAX_PEOPLE`` (8) people, ids of 1 to ``MAX_ID`` (16) bytes,
unique, steps up to 2**32 - 1. Anything else is rejected with ``PacketError``.

Exchange, as in the plan's sequence diagram: each badge sends its
contributions, stages the per-person max merge, sends an acknowledgement
carrying the merged total, and commits only when the peer's acknowledgement
for the same total has arrived. The ledger's confirmed total therefore changes
only on entering ``SUCCESS``. Merge-by-max is idempotent, so if one side
commits and the other times out (the two-generals case) a later retry heals
the stale side without double counting.
"""

import struct

from ledger import Exchange

MAGIC = b"WS"
VERSION = 1
TYPE_CONTRIBUTIONS = 1
TYPE_ACK = 2

HEADER_FORMAT = "<2sBB"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
ACK_FORMAT = "<I"
ACK_SIZE = struct.calcsize(ACK_FORMAT)

MAX_PEOPLE = 8
MAX_ID = 16
MAX_STEPS = 0xFFFFFFFF


class PacketError(ValueError):
    """A packet is malformed, foreign, or of an unsupported version."""


def pack_contributions(contributions):
    """contributions: {person_id: steps} -> bytes."""
    if not 1 <= len(contributions) <= MAX_PEOPLE:
        raise PacketError("people count")
    out = struct.pack(HEADER_FORMAT, MAGIC, VERSION, TYPE_CONTRIBUTIONS)
    out += struct.pack("<B", len(contributions))
    for pid in contributions:
        raw = pid.encode()
        steps = contributions[pid]
        if not 1 <= len(raw) <= MAX_ID:
            raise PacketError("id length")
        if not 0 <= steps <= MAX_STEPS:
            raise PacketError("steps range")
        out += struct.pack("<B", len(raw)) + raw + struct.pack("<I", steps)
    return out


def pack_ack(total):
    """total: the merged team total this badge staged -> bytes."""
    if not 0 <= total <= MAX_STEPS:
        raise PacketError("total range")
    return struct.pack(HEADER_FORMAT, MAGIC, VERSION, TYPE_ACK) + struct.pack(ACK_FORMAT, total)


def unpack(data):
    """Validate a packet and return (type, payload).

    payload is a {person_id: steps} dict for contributions and the merged
    total (int) for an acknowledgement. Raises PacketError otherwise.
    """
    if data is None or len(data) < HEADER_SIZE:
        raise PacketError("too short")
    magic, version, kind = struct.unpack_from(HEADER_FORMAT, data, 0)
    if magic != MAGIC:
        raise PacketError("magic")
    if version != VERSION:
        raise PacketError("version")
    if kind == TYPE_ACK:
        if len(data) != HEADER_SIZE + ACK_SIZE:
            raise PacketError("ack length")
        return kind, struct.unpack_from(ACK_FORMAT, data, HEADER_SIZE)[0]
    if kind != TYPE_CONTRIBUTIONS:
        raise PacketError("type")
    if len(data) < HEADER_SIZE + 1:
        raise PacketError("too short")
    count = data[HEADER_SIZE]
    if not 1 <= count <= MAX_PEOPLE:
        raise PacketError("people count")
    pos = HEADER_SIZE + 1
    people = {}
    for _ in range(count):
        if pos >= len(data):
            raise PacketError("truncated")
        n = data[pos]
        pos += 1
        if not 1 <= n <= MAX_ID or pos + n + 4 > len(data):
            raise PacketError("id length")
        try:
            pid = bytes(data[pos : pos + n]).decode()
        except UnicodeError:
            raise PacketError("id encoding")
        pos += n
        if pid in people:
            raise PacketError("duplicate id")
        people[pid] = struct.unpack_from("<I", data, pos)[0]
        pos += 4
    if pos != len(data):
        raise PacketError("trailing bytes")
    return kind, people


# --- session state machine -----------------------------------------------
WALKING = "walking"  # idle: counting steps, nothing being exchanged
HOLD = "hold"  # badges held back to back, holding steady
CONNECTING = "connecting"  # waiting for the link to come up
EXCHANGE = "exchange"  # contributions sent, waiting for the peer's
AWAITING_ACK = "awaiting_ack"  # peer's merge staged and acked, waiting for its ack
SUCCESS = "success"  # committed: show the celebration
UP_TO_DATE = "up_to_date"  # nothing new to share
SEPARATE = "separate"  # prompt to move the badges apart
RETRY = "retry"  # failed; previous total and pending steps are kept

STATES = (WALKING, HOLD, CONNECTING, EXCHANGE, AWAITING_ACK, SUCCESS, UP_TO_DATE, SEPARATE, RETRY)

# Why a retry happened (Session.retry_reason).
REASON_TIMEOUT = "timeout"
REASON_DROPPED = "dropped"
REASON_MISMATCH = "mismatch"
REASON_SEND_FAILED = "send_failed"
REASON_CANCELLED = "cancelled"

HOLD_MS = 1000  # steady hold before connecting
CONNECT_TIMEOUT_MS = 5000
EXCHANGE_TIMEOUT_MS = 5000  # per state: EXCHANGE and AWAITING_ACK
SUCCESS_MS = 3000  # celebration length
UP_TO_DATE_MS = 2000


class Session:
    """One deliberate back-to-back sync attempt at a time.

    Call ``begin_hold()`` when the hold is detected, then ``tick(dt_ms)`` every
    frame. At most one packet is handled per tick so every state is visible for
    at least a frame. Screens read ``state``, ``confirmed_total``, ``pending``,
    ``previous_total``, ``result_total``, ``result_added`` and ``retry_reason``.
    """

    def __init__(self, ledger, transport):
        self.ledger = ledger
        self.transport = transport
        self.state = WALKING
        self.state_ms = 0
        self.previous_total = None  # confirmed total before this attempt
        self.result_total = None  # confirmed total after a successful sync
        self.result_added = 0  # steps the sync added to the team total
        self.retry_reason = None
        self.rejected = 0  # packets ignored as malformed or foreign
        self._reset_attempt()

    # -- what screens need --
    @property
    def confirmed_total(self):
        return self.ledger.confirmed_total

    @property
    def pending(self):
        return self.ledger.pending

    # -- controls --
    def begin_hold(self):
        """Start an attempt from walking or after a retry. Returns True if started."""
        if self.state != WALKING and self.state != RETRY:
            return False
        self._reset_attempt()
        self.previous_total = self.ledger.confirmed_total
        self.result_total = None
        self.result_added = 0
        self.retry_reason = None
        self._drain()  # leftovers from an earlier attempt
        self._enter(HOLD)
        return True

    def cancel(self):
        """Abort: a hold goes back to walking, an exchange to retry, a retry to walking."""
        if self.state == HOLD or self.state == RETRY:
            self._clear_staged()
            self._enter(WALKING)
        elif self.state in (CONNECTING, EXCHANGE, AWAITING_ACK):
            self._retry(REASON_CANCELLED)

    def tick(self, dt_ms):
        self.state_ms += dt_ms
        state = self.state
        if state == HOLD:
            if self.state_ms >= HOLD_MS:
                self._enter(CONNECTING)
        elif state == CONNECTING:
            if self.transport.connected():
                self._start_exchange()
            elif self.state_ms >= CONNECT_TIMEOUT_MS:
                self._retry(REASON_TIMEOUT)
        elif state == EXCHANGE or state == AWAITING_ACK:
            self._poll()
            if self.state == EXCHANGE or self.state == AWAITING_ACK:
                if not self.transport.connected():
                    self._retry(REASON_DROPPED)
                elif self.state_ms >= EXCHANGE_TIMEOUT_MS:
                    self._retry(REASON_TIMEOUT)
        elif state == SUCCESS:
            if self.state_ms >= SUCCESS_MS:
                self._enter(SEPARATE)
        elif state == UP_TO_DATE:
            if self.state_ms >= UP_TO_DATE_MS:
                self._enter(SEPARATE)
        elif state == SEPARATE:
            self._drain()
            if not self.transport.connected():
                self._enter(WALKING)
        else:  # WALKING, RETRY: ignore stray packets from an old attempt
            self._drain()

    # -- internals --
    def _reset_attempt(self):
        self._sent = None  # contributions snapshot sent this attempt
        self._staged = None
        self._staged_total = 0
        self._peer_ack = None  # total from the peer's ack, once received
        self._ack_sent = False

    def _enter(self, state):
        self.state = state
        self.state_ms = 0

    def _drain(self):
        while self.transport.receive() is not None:
            pass

    def _send(self, data):
        try:
            self.transport.send(data)
        except OSError:
            return False
        return True

    def _clear_staged(self):
        if self._staged is not None:
            self.ledger.discard(self._staged)
        self._reset_attempt()

    def _retry(self, reason):
        self._clear_staged()
        self.retry_reason = reason
        self._enter(RETRY)

    def _start_exchange(self):
        # Snapshot now: steps counted during the exchange stay pending.
        self._sent = self.ledger.outgoing_contributions()
        if not self._send(pack_contributions(self._sent)):
            self._retry(REASON_SEND_FAILED)
            return
        self._enter(EXCHANGE)

    def _poll(self):
        data = self.transport.receive()
        if data is None:
            return
        try:
            kind, payload = unpack(data)
        except PacketError:
            self.rejected += 1
            return
        if kind == TYPE_CONTRIBUTIONS:
            if self._staged is None:
                self._on_contributions(payload)
        elif self._peer_ack is None:
            self._peer_ack = payload
        self._check_ack()

    def _on_contributions(self, remote):
        sent = self._sent
        merged = dict(sent)
        partner = None
        for pid in remote:
            if pid != self.ledger.me:
                partner = pid
            if remote[pid] > merged.get(pid, 0):
                merged[pid] = remote[pid]
        if partner is None:
            partner = self.ledger.partner
        folded = sent[self.ledger.me] - self.ledger.contributions.get(self.ledger.me, 0)
        # Same shape Ledger.receive builds, but from what we actually sent so
        # both badges merge identical inputs even if steps arrived meanwhile.
        staged = Exchange(merged, folded, partner)
        self._staged = staged
        self._staged_total = sum(merged.values())
        if not self._send(pack_ack(self._staged_total)):
            self._retry(REASON_SEND_FAILED)
            return
        self._ack_sent = True
        if self.ledger.confirmed_total is not None and folded == 0 and merged == self.ledger.contributions:
            self.ledger.discard(staged)
            self._staged = None
            self.result_total = self.ledger.confirmed_total
            self._enter(UP_TO_DATE)
            return
        self._enter(AWAITING_ACK)

    def _check_ack(self):
        if self._staged is None or self._peer_ack is None or not self._ack_sent:
            return
        if self.state != AWAITING_ACK:
            return
        if self._peer_ack != self._staged_total:
            self._retry(REASON_MISMATCH)
            return
        previous = self.ledger.confirmed_total
        self.ledger.commit(self._staged)
        self.previous_total = previous
        self.result_total = self.ledger.confirmed_total
        self.result_added = self.result_total - (previous or 0)
        self._staged = None
        self._enter(SUCCESS)
