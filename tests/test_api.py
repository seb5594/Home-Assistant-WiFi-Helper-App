"""HTTP front door: open inventory/ticket endpoints and the token-protected, optional capture endpoints."""
import http.client
import ipaddress
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "wifi_helper/app"))
import api
import captures
import protocol
import tickets

TOKEN = "capture-token-0123456789"
PCAP = protocol_header = b"\xd4\xc3\xb2\xa1\x02\x00\x04\x00" + b"\x00" * 16


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        (Path(self.directory.name) / "drone-20261126-101500.pcap").write_bytes(PCAP)
        self.tickets = tickets.TicketStore()
        self.log = Mock()
        self.start()

    def start(self, token=TOKEN):
        self.store = captures.CaptureStore(self.directory.name)
        self.server = api.HelperServer(("127.0.0.1", 0), ipaddress.ip_interface("172.30.32.1/23"), self.tickets,
                                       lambda: {"adapters": [], "usb_devices": [],
                                                "helper": {"protocol": protocol.PROTOCOL_VERSION}},
                                       self.store, token, self.log)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def call(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        connection.request(method, path, None if body is None else json.dumps(body), headers or {})
        response = connection.getresponse()
        data = response.read()
        connection.close()
        return response.status, data

    def authorized(self):
        return {"Authorization": f"Bearer {TOKEN}"}

    def test_inventory_and_ticket_need_no_secret(self):
        status, data = self.call("GET", "/v1/inventory")
        self.assertEqual((status, json.loads(data)["helper"]["protocol"]), (200, protocol.PROTOCOL_VERSION))
        status, data = self.call("POST", "/v1/tickets", {"protocol": protocol.PROTOCOL_VERSION, "operation": "lease", "interface": "wlan1"})
        self.assertEqual(status, 200)
        self.assertEqual(self.tickets.redeem(json.loads(data)["ticket"]), ("lease", "wlan1"))

    def test_ticket_request_with_other_protocol_or_bad_operation_is_refused(self):
        self.assertEqual(self.call("POST", "/v1/tickets", {"protocol": 3, "operation": "lease", "interface": "wlan1"})[0], 409)
        self.assertEqual(self.call("POST", "/v1/tickets", {"protocol": protocol.PROTOCOL_VERSION, "operation": "rm", "interface": "wlan1"})[0], 400)
        self.assertEqual(self.call("POST", "/v1/tickets")[0], 400)

    def test_peers_outside_the_app_network_get_no_inventory_or_tickets(self):
        handler = Mock(spec=api.Handler)
        handler.server = self.server
        handler.client_address = ("192.168.1.50", 40000)
        self.assertFalse(api.Handler.from_app_network(handler))
        handler.client_address = ("172.30.33.7", 40000)
        self.assertTrue(api.Handler.from_app_network(handler))

    def test_capture_requires_the_token(self):
        self.assertEqual(self.call("GET", "/v1/captures")[0], 401)
        self.assertEqual(self.call("GET", "/v1/captures", headers={"Authorization": "Bearer nope"})[0], 401)
        status, data = self.call("GET", "/v1/captures", headers=self.authorized())
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)["captures"][0]["name"], "drone-20261126-101500.pcap")

    def test_capture_endpoints_do_not_exist_while_the_feature_is_off(self):
        self.stop()
        self.start(token=None)
        self.assertEqual(self.call("GET", "/v1/captures", headers=self.authorized())[0], 404)

    def test_download_and_name_validation(self):
        status, data = self.call("GET", "/v1/captures/drone-20261126-101500.pcap", headers=self.authorized())
        self.assertEqual((status, data), (200, PCAP))
        for bad in ("../options.json", "..%2Foptions.json", "notes.txt", ".hidden.pcap"):
            self.assertIn(self.call("GET", "/v1/captures/" + bad, headers=self.authorized())[0], (400, 404))
        self.assertEqual(self.call("GET", "/v1/captures/missing.pcap", headers=self.authorized())[0], 404)

    def test_symlinks_are_never_served(self):
        link = Path(self.directory.name) / "link.pcap"
        link.symlink_to("/etc/hostname")
        self.assertEqual(self.call("GET", "/v1/captures/link.pcap", headers=self.authorized())[0], 404)
        self.assertEqual([item["name"] for item in self.store.listing()], ["drone-20261126-101500.pcap"])

    def test_filter_and_summary_use_tshark_with_validated_input(self):
        with patch.object(captures.CaptureStore, "_tshark", return_value=b"filtered") as tshark:
            status, data = self.call("GET", "/v1/captures/drone-20261126-101500.pcap?filter=udp.port%3D%3D6666", headers=self.authorized())
            self.assertEqual((status, data), (200, b"filtered"))
            self.assertIn("udp.port==6666", tshark.call_args.args[0])
            status, data = self.call("GET", "/v1/captures/drone-20261126-101500.pcap/summary", headers=self.authorized())
            self.assertEqual(status, 200)
            self.assertEqual(self.call("GET", "/v1/captures/drone-20261126-101500.pcap?filter=%00bad", headers=self.authorized())[0], 400)

    def test_delete(self):
        self.assertEqual(self.call("DELETE", "/v1/captures/drone-20261126-101500.pcap", headers=self.authorized())[0], 200)
        self.assertEqual(self.store.listing(), [])

    def test_host_capture_is_bounded_and_limited_to_existing_interfaces(self):
        for body in ({"interface": "../x", "seconds": 5}, {"interface": "nonexistent0", "seconds": 5},
                     {"interface": "lo", "seconds": 100000}):
            self.assertEqual(self.call("POST", "/v1/host-capture", body, self.authorized())[0], 400)
        with patch.object(captures.subprocess, "run") as run:
            status, data = self.call("POST", "/v1/host-capture", {"interface": "lo", "seconds": 5, "filter": "udp port 6666"}, self.authorized())
            self.assertEqual(status, 202)
            self.assertRegex(json.loads(data)["name"], r"^host-lo-\d{8}-\d{6}\.pcapng$")
            for _ in range(50):
                if run.called:
                    break
                threading.Event().wait(0.02)
            arguments = run.call_args.args[0]
            self.assertEqual(arguments[:3], ["tshark", "-i", "lo"])
            self.assertIn("duration:5", arguments)


class CaptureSettingsTests(unittest.TestCase):
    def test_disabled_by_default_and_token_is_validated(self):
        self.assertIsNone(captures.validate_settings({}))
        with patch.object(captures.shutil, "which", return_value="/usr/bin/tshark"):
            for token in ("", "short", "has space in the token!"):
                with self.assertRaises(captures.CaptureUnavailable):
                    captures.validate_settings({"capture_enabled": True, "capture_token": token})
            self.assertEqual(captures.validate_settings({"capture_enabled": True, "capture_token": TOKEN}), TOKEN)

    def test_missing_tshark_disables_the_feature_with_a_clear_reason(self):
        with patch.object(captures.shutil, "which", return_value=None), self.assertRaisesRegex(captures.CaptureUnavailable, "tshark"):
            captures.validate_settings({"capture_enabled": True, "capture_token": TOKEN})


if __name__ == "__main__":
    unittest.main()
