"""The client-side recorder writes files that Wireshark and tshark can read."""
from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sdk"))
from wifi_helper import capture


class PcapFormatTests(unittest.TestCase):
    def test_global_header_and_record_layout(self):
        magic, major, minor, _, _, snaplen, linktype = struct.unpack("<IHHiIII", capture.global_header())
        self.assertEqual((magic, major, minor, linktype), (0xA1B2C3D4, 2, 4, 1))
        record = capture.packet_record(b"\x01" * 60, 1700000000.25)
        seconds, micros, captured, original = struct.unpack("<IIII", record[:16])
        self.assertEqual((seconds, micros, captured, original, len(record)), (1700000000, 250000, 60, 60, 76))

    def test_snaplen_truncates_the_payload_but_keeps_the_original_length(self):
        record = capture.packet_record(b"\x02" * 100, 1.0, snaplen=64)
        self.assertEqual(struct.unpack("<II", record[8:16]), (64, 100))
        self.assertEqual(len(record), 16 + 64)

    def test_names_are_safe_and_old_files_are_pruned(self):
        self.assertRegex(capture.capture_name("../drone cam"), r"^drone-cam-\d{8}-\d{6}\.pcap$")
        self.assertRegex(capture.capture_name("***"), r"^capture-")
        with tempfile.TemporaryDirectory() as directory:
            for index in range(5):
                path = Path(directory) / f"old-{index}.pcap"
                path.write_bytes(b"x")
                path.touch()
                time.sleep(0.01)
            capture.prune(directory, keep=2)
            self.assertEqual(sorted(path.name for path in Path(directory).glob("*.pcap")), ["old-3.pcap", "old-4.pcap"])


@unittest.skipUnless(sys.platform == "linux", "AF_PACKET")
class RecorderTests(unittest.TestCase):
    def test_records_real_frames_from_loopback_into_a_parseable_file(self):
        import socket
        with tempfile.TemporaryDirectory() as directory:
            try:
                recorder = capture.PcapRecorder("lo", "unit", directory).start()
            except (PermissionError, OSError) as exc:
                self.skipTest(f"raw sockets unavailable: {exc}")
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                sender.sendto(b"marker-6666", ("127.0.0.1", 6666))
            time.sleep(0.8)
            recorder.stop()
            data = recorder.path.read_bytes()
            self.assertIsNone(recorder.error)
            self.assertEqual(struct.unpack("<I", data[:4])[0], 0xA1B2C3D4)
            self.assertIn(b"marker-6666", data)
            offset, count = 24, 0
            while offset < len(data):  # Every record header must point exactly at the next one.
                captured = struct.unpack("<I", data[offset + 8:offset + 12])[0]
                offset += 16 + captured
                count += 1
            self.assertEqual((offset, count > 0), (len(data), True))


if __name__ == "__main__":
    unittest.main()
