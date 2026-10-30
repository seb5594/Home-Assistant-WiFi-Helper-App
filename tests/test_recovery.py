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
class RecoveryTests(unittest.TestCase):


    @unittest.skipUnless(sys.platform == "linux", "Linux namespace descriptor type check")
    def test_return_rejects_regular_file_before_any_radio_mutation(self):
        import os
        active = lease.Lease.__new__(lease.Lease)
        active.options, active.interface, active.phy = {}, "wlan1", "phy3"
        active.closed, active.sock, active.journal = threading.Event(), Mock(), Mock()
        with tempfile.TemporaryFile() as file:
            descriptor = os.dup(file.fileno())
            with patch.object(lease, "connect", return_value=Mock(__enter__=Mock(return_value=Mock()), __exit__=Mock(return_value=False))), \
                 patch.object(lease, "send"), patch.object(lease, "receive", return_value=({"event": "return_target", "phy": "phy3"}, [descriptor])), \
                 patch.object(lease.subprocess, "run") as mutate:
                with self.assertRaises((OSError, RuntimeError)):
                    active.release(Adapter("wlan1", "phy3", 3))
            mutate.assert_not_called()
            with self.assertRaises(OSError):
                os.fstat(descriptor)


    def recover(self, *, mac=MAC, details=DETAILS, addresses=None, duplicate=False):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        data = Path(temp.name)
        recovery = data / "recovery.json"
        recovery.write_text(json.dumps(SNAPSHOT))
        calls = []
        def command(*args):
            calls.append(args)
            if args == ("iw", "dev"):
                text = "phy#6\n\tInterface wlan1\n\t\ttype managed\n"
                return text + ("phy#7\n\tInterface wlan2\n\t\ttype managed\n" if duplicate else "")
            if args[-1] == "link":
                return "Not connected."
            if args[:2] == ("ip", "-j"):
                return json.dumps([{"address": mac, "addr_info": addresses or []}])
            return ""
        with patch.object(broker, "DATA", data), patch.object(broker, "command", side_effect=command), \
             patch.object(broker, "adapter_details", return_value=details), patch.object(broker, "inspect"), \
             patch.object(broker, "nm_properties", return_value=True), \
             patch.object(broker, "nm_set") as nm:
            try:
                broker.restore(dict(SNAPSHOT), Mock(), wait=0)
            finally:
                self.calls, self.recovery, self.nm_calls = calls, recovery, nm.call_args_list


    def test_same_usb_mac_and_port_with_new_phy_restores(self):
        self.recover()
        self.assertFalse(self.recovery.exists())
        self.assertEqual(self.nm_calls[0].args, ("wlan1", True))


    def test_wrong_mac_or_port_and_ambiguous_identity_never_mutated(self):
        for options in ({"mac": "00:11:22:33:44:55"}, {"details": {**DETAILS, "usb_path": "2-3"}}, {"duplicate": True}):
            with self.subTest(options=options), self.assertRaises(PreflightError):
                self.recover(**options)
            self.assertTrue(self.recovery.exists())
            self.assertFalse(self.nm_calls)
            self.assertFalse(any("set" in call for call in self.calls))


    def test_replugged_but_active_adapter_not_disconnected_for_recovery(self):
        with self.assertRaises(PreflightError):
            self.recover(addresses=[{"local": "192.168.1.50"}])
        self.assertFalse(self.nm_calls)
        self.assertTrue(self.recovery.exists())


    def test_no_adapter_exits_immediately_preserving_existing_recovery(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            data = Path(directory)
            (data / "options.json").write_text(json.dumps({"pairing_token": "x"*40}))
            (data / "recovery.json").write_text(json.dumps(SNAPSHOT))
            with patch.object(broker, "DATA", data), patch.object(broker, "command", return_value=""), \
                 patch.object(broker, "usb_devices", return_value=[]), patch.object(broker, "restore") as restore:
                self.assertEqual(broker.main(), 1)
            restore.assert_not_called()
            self.assertTrue((data / "recovery.json").exists())
            self.assertIn("No wireless network interface detected", (data / "logs/app.log").read_text())

