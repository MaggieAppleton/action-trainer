"""Round-trip the Walk Together advertisement packet."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "walk_together"))

import packet  # noqa: E402
import protocol  # noqa: E402


class PacketTests(unittest.TestCase):
    def test_round_trip_large_total(self):
        data = packet.pack_mfg(0xDEADBEEF, 0x01020304, 1950000, 513)
        got = packet.unpack_mfg(data)
        self.assertEqual(got["badge_id"], 0xDEADBEEF)
        self.assertEqual(got["partner_id"], 0x01020304)
        self.assertEqual(got["steps"], 1950000)
        self.assertEqual(got["seq"], 513)
        self.assertEqual(got["magic"], b"WT")
        self.assertEqual(got["ver"], packet.VERSION)

    def test_unpaired_partner_is_zero(self):
        self.assertEqual(packet.unpack_mfg(packet.pack_mfg(7, 0, 70000, 1))["partner_id"], 0)

    def test_total_above_u16(self):
        self.assertEqual(packet.unpack_mfg(packet.pack_mfg(1, 2, 65536, 0))["steps"], 65536)

    def test_full_advertisement_fits_31_bytes(self):
        adv = packet.pack_adv(0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFF)
        self.assertLessEqual(len(adv), 31)
        self.assertEqual(adv[:3], bytes((2, 0x01, 0x06)))
        self.assertEqual(adv[3], len(adv) - 4)
        self.assertEqual(adv[4], 0xFF)
        self.assertEqual(packet.unpack_mfg(adv[5:])["steps"], 0xFFFFFFFF)

    def test_truncated_returns_none(self):
        data = packet.pack_mfg(1, 2, 3, 4)
        self.assertIsNone(packet.unpack_mfg(data[:-1]))
        self.assertIsNone(packet.unpack_mfg(b""))

    def test_airtime_packet_rejected(self):
        at = protocol.pack_mfg(1, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.assertIsNone(packet.unpack_mfg(at))

    def test_unknown_version_rejected(self):
        data = bytearray(packet.pack_mfg(1, 2, 3, 4))
        data[4] = packet.VERSION + 1
        self.assertIsNone(packet.unpack_mfg(bytes(data)))

    def test_walk_packet_not_airtime(self):
        self.assertIsNone(protocol.unpack_mfg(packet.pack_mfg(1, 2, 3, 4)))


if __name__ == "__main__":
    unittest.main()
