"""HTTP front door of the helper, reachable by host name from other Home Assistant apps.

Open to the app network: adapter inventory and tickets (a ticket is only useful together with
the private socket in /share). Protected by the capture token: everything below /v1/captures,
which can also be reached from outside Home Assistant when ``listen_address`` allows it.
"""
import select
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from urllib.parse import parse_qs, urlsplit

from captures import CaptureStore, CaptureUnavailable, token_matches
from protocol import PROTOCOL_VERSION
from wifi import PreflightError, command

# Home Assistant's internal Docker network; the Supervisor gateway is the host as seen by apps.
FALLBACK_NETWORK = ipaddress.ip_interface("172.30.32.1/23")
MAX_BODY = 4096


def app_network():
    """Address of the host on Home Assistant's internal bridge, as an interface (address plus prefix)."""
    try:
        for entry in json.loads(command("ip", "-j", "-4", "address", "show", "dev", "hassio")):
            for info in entry.get("addr_info", []):
                return ipaddress.ip_interface(f"{info['local']}/{info['prefixlen']}")
    except (PreflightError, ValueError, KeyError, IndexError):
        pass
    return FALLBACK_NETWORK


class HelperServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, network, tickets, inventory, captures, capture_token, log):
        self.network, self.tickets, self.inventory = network, tickets, inventory
        self.captures, self.capture_token, self.log = captures, capture_token, log
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "WiFiHelper"
    sys_version = ""

    def log_message(self, *_):
        pass  # The journal records decisions; per-request access logs only waste flash writes.

    # -- helpers ---------------------------------------------------------------------------
    def reply(self, status, body, content_type="application/json"):
        data = body if isinstance(body, bytes) else (body if isinstance(body, str) else json.dumps(body)).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def error(self, status, text):
        self.reply(status, {"error": text})

    def from_app_network(self):
        try:
            address = ipaddress.ip_address(self.client_address[0])
        except ValueError:
            return False
        return address.is_loopback or address in self.server.network.network

    def capture_allowed(self):
        if self.server.capture_token is None:
            self.error(404, "Capture is disabled; enable it and set a capture token in the helper configuration")
        elif not token_matches(self.headers.get("Authorization"), self.server.capture_token):
            self.send_response(401)
            self.send_header("WWW-Authenticate", "Bearer")
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            return True
        return False

    def read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= MAX_BODY:
            raise ValueError("Request body required")
        body = json.loads(self.rfile.read(length))
        if not isinstance(body, dict):
            raise ValueError("Request body must be an object")
        return body

    def dispatch(self, method):
        url = urlsplit(self.path)
        query = {key: values[-1] for key, values in parse_qs(url.query).items()}
        parts = [part for part in url.path.split("/") if part]
        try:
            if parts[:2] == ["v1", "captures"] or parts[:2] == ["v1", "host-capture"]:
                if self.capture_allowed():
                    self.capture_route(method, parts[1:], query)
            elif not self.from_app_network():
                self.error(403, "Only apps on the Home Assistant network may use this endpoint")
            elif (method, parts) == ("GET", ["v1", "inventory"]):
                self.reply(200, self.server.inventory())
            elif (method, parts) == ("POST", ["v1", "tickets"]):
                body = self.read_json()
                if body.get("protocol") != PROTOCOL_VERSION:
                    self.error(409, "Protocol mismatch; update both apps")
                else:
                    self.reply(200, {"ticket": self.server.tickets.issue(body.get("operation"), body.get("interface"))})
            else:
                self.error(404, "Unknown endpoint")
        except FileNotFoundError:
            self.error(404, "Capture not found")
        except CaptureUnavailable as exc:
            self.error(503, str(exc))
        except (ValueError, KeyError) as exc:
            self.error(400, str(exc))

    def capture_route(self, method, parts, query):
        store: CaptureStore = self.server.captures
        if parts == ["captures"] and method == "GET":
            self.reply(200, {"captures": store.listing()})
        elif parts == ["host-capture"] and method == "POST":
            body = self.read_json()
            name = store.record_host(body.get("interface"), body.get("seconds", 60), body.get("filter", ""))
            self.server.log("info", f"Host capture started on {body.get('interface')}: {name}")
            self.reply(202, {"name": name})
        elif len(parts) == 2 and parts[0] == "captures" and method == "GET":
            self.stream_capture(store, parts[1], query)
        elif len(parts) == 2 and parts[0] == "captures" and method == "DELETE":
            store.delete(parts[1])
            self.reply(200, {"deleted": parts[1]})
        elif len(parts) == 3 and parts[0] == "captures" and parts[2] == "summary" and method == "GET":
            self.reply(200, store.summary(parts[1], query.get("filter")), "text/plain; charset=utf-8")
        else:
            self.error(404, "Unknown endpoint")

    def stream_capture(self, store, name, query):
        path = store.path(name)  # Validates the name and raises FileNotFoundError.
        if query.get("filter"):
            self.reply(200, store.filtered(name, query["filter"]), "application/vnd.tcpdump.pcap")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.tcpdump.pcap")
        self.send_header("Cache-Control", "no-store")
        if query.get("follow") != "1":
            self.send_header("Content-Length", str(path.stat().st_size))
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            if query.get("follow") == "1":
                store.follow(name, self.wfile.write, self.viewer_connected)
            else:
                with path.open("rb") as file:
                    while chunk := file.read(65536):
                        self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def viewer_connected(self):
        """False once the viewer closed its end, even while the followed file is idle."""
        readable, _, _ = select.select([self.connection], [], [], 0)
        return not readable or bool(self.connection.recv(1, socket.MSG_PEEK))

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    def do_DELETE(self):
        self.dispatch("DELETE")
