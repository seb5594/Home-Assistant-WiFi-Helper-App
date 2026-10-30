import contextlib
from http.client import HTTPConnection
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'wifi_helper/app'))
import wifi,protocol,broker,lease,inventory
from wifi import Adapter,radio_unblocked,PreflightError
from journal import Journal
IW = "phy#0\n\tInterface wlan1\n\t\tifindex 4\n\t\ttype managed\n"
INFO = "Wiphy phy0\n\tSupported interface modes:\n\t\t * managed\n\t\t * AP\n\tBand 1:\n"
CANDIDATE = {"name": "wlan1", "phy": "phy0", "type": "managed"}
MAC = "02:00:00:00:00:01"
SNAPSHOT = {"name": "wlan1", "phy": "phy3", "mac": MAC, "bus": "USB", "usb_path": "2-2.2", "driver": "ath9k_htc", "up": False, "managed": True}
DETAILS = {"bus": "USB", "usb_path": "2-2.2", "driver": "ath9k_htc"}
class RfkillTests(unittest.TestCase):
    def test_stale_unrelated_entry_does_not_hide_valid_radio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "rfkill3").mkdir()  # name missing after another PHY moved namespaces
            selected = root / "rfkill4"
            selected.mkdir()
            for key, value in {"name": "phy0", "soft": "0", "hard": "0"}.items():
                (selected / key).write_text(value)
            radio_unblocked("phy0", root)
            for key in ("soft", "hard"):
                for value in ("1", "", "unknown"):
                    (selected / key).write_text(value)
                    with self.assertRaises(PreflightError):
                        radio_unblocked("phy0", root)
                (selected / key).write_text("0")
            (selected / "hard").unlink()
            with self.assertRaisesRegex(PreflightError, "became unavailable"):
                radio_unblocked("phy0", root)

    def test_missing_selected_radio_still_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "rfkill3").mkdir()
            with self.assertRaisesRegex(PreflightError, "cannot verify"):
                radio_unblocked("phy0", root)


class LogTests(unittest.TestCase):
    def test_restart_and_clear_delete_only_owned_logs_and_reset_replay(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory)
            for name in ("app.log", "app.log.1", "app.log.5", "keep.txt"):
                (root / name).write_text("old")
            journal = Journal(root)
            try:
                self.assertEqual([p.name for p in root.iterdir()], ["keep.txt"])
                journal.emit("info", "old terminal", "terminal")
                old = journal.snapshot(0)
                (root / "app.log.2").write_text("old")
                generation = journal.clear()
                journal.emit("info", "new terminal", "terminal")
                self.assertNotEqual(generation, old["generation"])
                fresh = journal.snapshot(99999, old["generation"])
                self.assertEqual(fresh["cursor"], 3)
                self.assertNotIn("old terminal", json.dumps(fresh))
                self.assertIn("new terminal", json.dumps(fresh))
                self.assertFalse((root / "app.log.2").exists())
                self.assertNotIn("old terminal", (root / "app.log").read_text())
                self.assertEqual((root / "keep.txt").read_text(), "old")
            finally:
                journal.close()


@unittest.skipUnless(sys.platform == "linux", "Linux sysfs-style symlinks and Unix sockets")
class UsbTests(unittest.TestCase):
    def test_assigned_usb_radio_is_not_reported_as_missing_driver(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            device = root / "2-2.2"
            device.mkdir()
            for key, value in {"idVendor": "0cf3", "idProduct": "9271", "product": "UB91"}.items():
                (device / key).write_text(value)
            lease = {"name": "wlp4s0f3u2u2", "bus": "USB", "usb_path": "2-2.2"}
            row = inventory.usb_devices(root, leased=lease)[0]
            self.assertEqual(row["assigned_interface"], lease["name"])
            self.assertIn("Assigned", row["hint"])
            self.assertNotIn("requires", row["hint"])
            row = inventory.usb_devices(root, leased={**lease, "usb_path": "2-3"})[0]
            self.assertIsNone(row["assigned_interface"])
            self.assertIn("requires", row["hint"])

    def test_additional_driver_families_detected_without_interface_name_assumptions(self):
        for name in ("rt2800usb", "mt7921u", "mwifiex_usb", "ath6kl_usb", "brcmfmac", "rtw_8822bu"):
            with self.subTest(driver=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                device = root / "1-1"
                device.mkdir()
                (device / "idVendor").write_text("1234")
                (device / "idProduct").write_text("5678")
                child = root / "1-1:1.0"
                child.mkdir()
                driver = root / name
                driver.mkdir()
                (child / "driver").symlink_to(driver, target_is_directory=True)
                self.assertEqual(inventory.usb_devices(root)[0]["drivers"], [name])

    def test_host_module_inventory_reports_observed_modules_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("ath9k_htc", "rtw88_8822ce", "mt7921u", "unrelated"):
                (root / name).mkdir()
            info = inventory.host_drivers(root)
            self.assertEqual(info["loaded_wifi_modules"], ["ath9k_htc", "mt7921u", "rtw88_8822ce"])
            self.assertTrue(info["kernel"])

    def test_ar9271_usb_enumeration_distinguished_from_bound_wifi(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            device = root / "2-2.2"
            device.mkdir()
            for key, value in {"idVendor": "0cf3", "idProduct": "9271", "product": "UB91"}.items():
                (device / key).write_text(value)
            first = inventory.usb_devices(root)[0]
            self.assertEqual(first["id"], "0cf3:9271")
            self.assertEqual(first["drivers"], [])
            self.assertIn("ath9k_htc", first["hint"])
            interface = root / "2-2.2:1.0"
            (interface / "net/wlan1").mkdir(parents=True)
            driver = root / "ath9k_htc"
            driver.mkdir()
            (interface / "driver").symlink_to(driver, target_is_directory=True)
            second = inventory.usb_devices(root)[0]
            self.assertEqual(second["interfaces"], ["wlan1"])
            self.assertEqual(second["drivers"], ["ath9k_htc"])
            self.assertEqual(second["hint"], "")

