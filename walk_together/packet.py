"""Walk Together advertisement packet (badge-to-badge, Bluetooth LE).

Distinct from the airtime packet in protocol.py (magic "AT"); that format is
untouched. Each badge advertises its own cumulative step total (u32, so it
does not wrap during a conference) and the partner id it is paired with
(0 when unpaired). Legacy advertising leaves 31 bytes: flags (3) +
manufacturer AD header (2) + this 19-byte body = 24 bytes.

Only `struct` is used so the module runs under MicroPython.
"""

import struct

COMPANY_ID = 0xFFFF
MAGIC = b"WT"
VERSION = 1
MFG_FORMAT = "<H2sBIIIH"
MFG_SIZE = struct.calcsize(MFG_FORMAT)

FIELDS = ("company", "magic", "ver", "badge_id", "partner_id", "steps", "seq")


def pack_mfg(badge_id, partner_id, steps, seq):
    """Manufacturer data including the 2-byte company ID."""
    return struct.pack(
        MFG_FORMAT,
        COMPANY_ID,
        MAGIC,
        VERSION,
        badge_id & 0xFFFFFFFF,
        partner_id & 0xFFFFFFFF,
        steps & 0xFFFFFFFF,
        seq & 0xFFFF,
    )


def adv_payload(mfg):
    return bytes((2, 0x01, 0x06, len(mfg) + 1, 0xFF)) + mfg


def pack_adv(badge_id, partner_id, steps, seq):
    """Full advertisement payload (flags AD + manufacturer AD)."""
    return adv_payload(pack_mfg(badge_id, partner_id, steps, seq))


def unpack_mfg(data):
    """Decode manufacturer data including company ID; None if not a walk packet."""
    if len(data) < MFG_SIZE:
        return None
    values = struct.unpack(MFG_FORMAT, data[:MFG_SIZE])
    if values[0] != COMPANY_ID or values[1] != MAGIC or values[2] != VERSION:
        return None
    return dict(zip(FIELDS, values))
