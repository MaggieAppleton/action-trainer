"""Round-trip the GATT stream packet format shared by badge and recorder."""
import unittest

import protocol  # noqa: E402


class StreamTests(unittest.TestCase):
    def test_round_trip(self):
        rows = [(70000 + i * 11, -32768, 32767, 16384, -5, 0, 7, 0x84, i % 6) for i in range(8)]
        packet = protocol.pack_samples(65537, [protocol.pack_sample(*r) for r in rows])
        self.assertEqual(len(packet), protocol.STREAM_HEADER_SIZE + 8 * protocol.SAMPLE_SIZE)
        seq, samples = protocol.unpack_samples(packet)
        self.assertEqual(seq, 1)
        self.assertEqual(samples, [((r[0] & 0xFFFF),) + r[1:] for r in rows])

    def test_fits_negotiated_mtu(self):
        self.assertLessEqual(protocol.STREAM_HEADER_SIZE + 8 * protocol.SAMPLE_SIZE, 527 - 3)
        self.assertLessEqual(protocol.STREAM_HEADER_SIZE + protocol.SAMPLE_SIZE, 23 - 3)

    def test_truncated_packet(self):
        packet = protocol.pack_samples(0, [protocol.pack_sample(0, 1, 2, 3, 4, 5, 6, 0, 0)] * 2)
        _, samples = protocol.unpack_samples(packet[:-1])
        self.assertEqual(len(samples), 1)


if __name__ == "__main__":
    unittest.main()
