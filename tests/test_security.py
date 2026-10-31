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
class DiscoveryTests(unittest.TestCase):
    def run_fake(self, *, flags=None, addresses=None, master=None, routes=None, info=INFO, link="Not connected."):
        def run(*args):
            if args[:2] == ("iw", "phy"):
                return info
            if args[:3] == ("ip", "-j", "address"):
                return json.dumps([{"ifindex": 4, "flags": flags or [], "addr_info": addresses or [], "master": master}])
            if args[0] == "ip":
                return json.dumps(routes or [])
            return link
        return run

    def test_free_ap_adapter_is_accepted_without_mutations(self):
        calls = []
        run = self.run_fake()
        def traced(*args):
            calls.append(args)
            return run(*args)
        adapter = wifi.inspect(CANDIDATE, [CANDIDATE], run=traced)
        self.assertEqual(adapter.name, "wlan1")
        self.assertFalse(any("set" in c or "flush" in c or "disconnect" in c for c in calls))

    def test_rejects_host_management_radio_routes_and_shared_phy(self):
        cases = [
            self.run_fake(flags=["UP"]),
            self.run_fake(addresses=[{"local": "192.168.1.5"}]),
            self.run_fake(master="br0"),
            self.run_fake(routes=[{"dst": "default", "dev": "wlan1"}]),
            self.run_fake(routes=[{"nexthops": [{"dev": "wlan1"}]}]),
            self.run_fake(link="Connected to 00:11:22:33:44:55"),
        ]
        for run in cases:
            with self.subTest(run=run), self.assertRaises(wifi.PreflightError):
                wifi.inspect(CANDIDATE, [CANDIDATE], run=run)
        with self.assertRaises(wifi.PreflightError):
            wifi.inspect(CANDIDATE, [CANDIDATE, {**CANDIDATE, "name": "wlan1-ap"}], run=self.run_fake())

    def test_ap_exact_mode_required(self):
        for modes in ("managed", "managed\n\t\t * AP/VLAN", "managed\n\t\t * P2P-GO"):
            with self.subTest(modes=modes), self.assertRaises(wifi.PreflightError):
                wifi.inspect(CANDIDATE, [CANDIDATE], run=self.run_fake(info=INFO.replace("managed\n\t\t * AP", modes)))

    def test_host_idle_up_is_allowed_but_associated_is_not(self):
        wifi.inspect(CANDIDATE, [CANDIDATE], run=self.run_fake(flags=["UP"]), allow_up=True)
        with self.assertRaises(wifi.PreflightError):
            wifi.inspect(CANDIDATE, [CANDIDATE], run=self.run_fake(flags=["UP"], link="Connected"), allow_up=True)

    def test_networkmanager_missing_or_active_fails_closed(self):
        with patch("wifi.bus", side_effect=[str("/device/1"), True, 100, "/active/1"]):
            with self.assertRaises(wifi.PreflightError):
                wifi.nm_unmanaged("wlan1")
        with patch("wifi.bus", side_effect=wifi.PreflightError("bus unavailable")):
            with self.assertRaises(wifi.PreflightError):
                wifi.nm_unmanaged("wlan1")

    def test_no_adapter_startup_and_no_automatic_fallback(self):
        with patch("wifi.command", return_value=""):
            with self.assertRaises(wifi.PreflightError):
                wifi.discover("wlan1", lambda *_: None)
        with patch("wifi.command", return_value=IW):
            with self.assertRaises(wifi.PreflightError):
                wifi.discover("wlan9", lambda *_: None)

    def test_cleanup_refuses_replaced_adapter(self):
        with patch("wifi.same_device", side_effect=wifi.PreflightError("replaced")), patch("wifi.command") as run:
            self.assertFalse(wifi.cleanup(wifi.Adapter("wlan1", "phy0", 4), lambda *_: None))
            run.assert_not_called()


class LeaseTests(unittest.TestCase):


    def test_host_validation_accepts_phy_info_without_namespace_command_text(self):
        for name in ("wlp2s0", "wlp4s0f3u2u2"):
            def radio(*args):
                if args == ("iw", "dev"):
                    return IW.replace("wlan1", name)
                if args[:2] == ("iw", "phy"):
                    return INFO + "\tSupported commands:\n\t\t * new_interface\n\t\t * connect\n"
                if args[-2:] == ("get", "power_save"):
                    return "Power save: on"
                if args[0] == "ip" and args[2] in ("address", "link"):
                    return json.dumps([{"ifindex": 4, "address": "dc:e9:94:8c:9a:1b", "flags": ["UP"], "addr_info": []}])
                if args[0] == "ip":
                    return "[]"
                return "Not connected."
            def inspect(candidate, interfaces, **kwargs):
                return wifi.inspect(candidate, interfaces, run=radio, **kwargs)
            with self.subTest(name=name), patch.object(broker, "command", side_effect=radio), \
                 patch.object(broker, "inspect", side_effect=inspect), patch.object(broker, "nm_properties", return_value=True), \
                 patch.object(broker, "radio_unblocked"), patch.object(broker, "nm_set") as mutate:
                adapter, snapshot = broker.validate_host(name, lambda *_: None)
                self.assertEqual(adapter.name, name)
                self.assertEqual(snapshot["power_save"], "on")
                mutate.assert_not_called()


    def test_kernel_rejected_namespace_move_still_restores_and_fails(self):
        from types import SimpleNamespace
        adapter = wifi.Adapter("wlan1", "phy0", 4)
        snapshot = {"managed": True, "name": "wlan1", "phy": "phy0"}
        with tempfile.TemporaryDirectory() as temp, patch.object(broker, "DATA", Path(temp)), \
             patch.object(broker, "check_target"), patch.object(broker, "validate_host", return_value=(adapter, snapshot)), \
             patch.object(broker, "nm_set"), patch.object(broker, "command", return_value=IW), \
             patch.object(broker, "inspect"), patch.object(broker.subprocess, "run", return_value=SimpleNamespace(returncode=1, stderr="Operation not supported")), \
             patch.object(broker, "restore") as restore:
            with self.assertRaisesRegex(wifi.PreflightError, "Namespace handover failed.*Operation not supported"):
                broker.handover(8, "wlan1", lambda *_: None)
            restore.assert_called_once_with(snapshot, unittest.mock.ANY, wait=2)


    @unittest.skipUnless(sys.platform == "linux", "Linux namespace/SCM_RIGHTS API")
    def test_real_fd_transport_and_namespace_type_rejection(self):
        left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        with open("/proc/self/ns/net", "rb") as original:
            protocol.send(left, {"interface": "wlan1"}, original.fileno())
            data, fds = protocol.receive(right)
            self.assertEqual(data["interface"], "wlan1")
            self.assertEqual(os.fstat(fds[0]).st_ino, os.fstat(original.fileno()).st_ino)
            try:
                with self.assertRaises(ValueError):  # Cannot move a radio to the host's own namespace.
                    broker.check_target(fds[0])
            finally:
                os.close(fds[0])
        with tempfile.TemporaryFile() as file:
            with self.assertRaises(OSError):
                broker.check_target(file.fileno())


    @unittest.skipUnless(sys.platform == "linux", "Linux Unix socket transport")
    def test_mutual_authentication_and_wrong_secret(self):
        for correct in (True, False):
            left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            left.settimeout(2)
            right.settimeout(2)
            errors = []
            def helper():
                try:
                    protocol.server_authenticate(right, "wlan1", "private-" * 5)
                except Exception as exc:
                    errors.append(exc)
                finally:
                    right.close()
            thread = threading.Thread(target=helper)
            thread.start()
            try:
                if correct:
                    protocol.client_authenticate(left, "wlan1", "private-" * 5)
                else:
                    with self.assertRaises((ValueError, ConnectionError)):
                        protocol.client_authenticate(left, "wlan1", "incorrect-" * 5)
            finally:
                left.close()
                thread.join(3)
            self.assertEqual(bool(errors), not correct)


    def test_failed_handover_restores_host_state(self):
        adapter = wifi.Adapter("wlan1", "phy0", 4)
        snapshot = {"managed": True, "name": "wlan1", "phy": "phy0"}
        with tempfile.TemporaryDirectory() as temp, patch.object(broker, "DATA", Path(temp)), \
             patch.object(broker, "check_target"), patch.object(broker, "validate_host", return_value=(adapter, snapshot)), \
             patch.object(broker, "nm_set"), patch.object(broker, "command", return_value=IW), \
             patch.object(broker, "inspect"), patch.object(broker.subprocess, "run", side_effect=OSError("driver unavailable")), \
             patch.object(broker, "restore") as restore:
            with self.assertRaises(OSError):
                broker.handover(8, "wlan1", lambda *_: None)
            restore.assert_called_once_with(snapshot, unittest.mock.ANY, wait=2)
