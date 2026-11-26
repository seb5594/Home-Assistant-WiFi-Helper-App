"""Optional packet capture: serve pcap files and run tshark so Wireshark on another computer can look at them.

Everything here is disabled unless ``capture_enabled`` is set together with a ``capture_token``.
Client apps record their own leased radio (``wifi_helper.capture``); this module only stores,
serves and analyses those files, and can additionally record host-side interfaces on request.
"""
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time

from protocol import CAPTURE_DIR

NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}\.pcap(?:ng)?")
INTERFACE = re.compile(r"[A-Za-z0-9_.-]{1,15}")
MIN_TOKEN_LENGTH = 16
MAX_HOST_CAPTURE_SECONDS = 600
MAX_HOST_CAPTURE_BYTES = 128 * 1024 * 1024
ANALYSIS_TIMEOUT = 30
ANALYSIS_LIMIT = 256 * 1024
FOLLOW_LIMIT = 3600
DISPLAY_FILTER = re.compile(r"[\x20-\x7e]{1,256}")


class CaptureUnavailable(RuntimeError):
    """The optional capture feature is off, misconfigured or tshark is missing."""


def validate_settings(options):
    """Return the token when capture is correctly enabled, ``None`` when it is off; raise if misconfigured."""
    if not options.get("capture_enabled"):
        return None
    token = options.get("capture_token") or ""
    if len(token) < MIN_TOKEN_LENGTH or any(not 33 <= ord(char) <= 126 for char in token):
        raise CaptureUnavailable(f"capture_token needs at least {MIN_TOKEN_LENGTH} printable characters without spaces")
    if not shutil.which("tshark"):
        raise CaptureUnavailable("tshark is not installed in this image")
    return token


def token_matches(header, token):
    """Constant-time check of an ``Authorization: Bearer`` header."""
    return hmac.compare_digest((header or "").encode(), f"Bearer {token}".encode())


class CaptureStore:
    def __init__(self, directory=CAPTURE_DIR):
        self.directory = Path(directory)
        self._host_lock = threading.Lock()

    def path(self, name):
        """Resolve a user supplied file name inside the capture folder; refuse anything else."""
        if not NAME.fullmatch(name or ""):
            raise ValueError("Invalid capture name")
        path = self.directory / name
        if path.is_symlink() or not path.is_file():
            raise FileNotFoundError(name)
        return path

    def listing(self):
        files = []
        for path in sorted(self.directory.glob("*.pcap*"), key=lambda item: item.stat().st_mtime, reverse=True):
            if NAME.fullmatch(path.name) and path.is_file() and not path.is_symlink():
                info = path.stat()
                files.append({"name": path.name, "bytes": info.st_size, "modified": int(info.st_mtime)})
        return files[:100]

    def delete(self, name):
        self.path(name).unlink()

    def follow(self, name, write, alive=lambda: True):
        """Stream a file and keep sending what is appended, like ``tail -f``, until the viewer disconnects."""
        deadline = time.monotonic() + FOLLOW_LIMIT
        with self.path(name).open("rb") as file:
            while alive() and time.monotonic() < deadline:
                chunk = file.read(65536)
                if chunk:
                    write(chunk)
                else:
                    time.sleep(0.25)

    @staticmethod
    def _tshark(arguments, binary="tshark"):
        result = subprocess.run([binary, *arguments], capture_output=True, timeout=ANALYSIS_TIMEOUT)
        if result.returncode:
            raise CaptureUnavailable(result.stderr.decode(errors="replace").strip()[:500] or f"tshark exited {result.returncode}")
        return result.stdout

    def filtered(self, name, display_filter):
        """Return the packets of a file that match a Wireshark display filter, as a new pcap byte string."""
        if not DISPLAY_FILTER.fullmatch(display_filter):
            raise ValueError("Invalid display filter")
        return self._tshark(["-r", str(self.path(name)), "-Y", display_filter, "-w", "-", "-F", "pcap"])

    def summary(self, name, display_filter=None):
        """Plain text overview: conversations per protocol, so a first look needs no Wireshark at all."""
        arguments = ["-r", str(self.path(name)), "-q", "-z", "conv,ip", "-z", "conv,udp", "-z", "conv,tcp"]
        if display_filter:
            if not DISPLAY_FILTER.fullmatch(display_filter):
                raise ValueError("Invalid display filter")
            arguments[2:2] = ["-Y", display_filter]
        return self._tshark(arguments)[:ANALYSIS_LIMIT].decode(errors="replace")

    def record_host(self, interface, seconds, capture_filter=""):
        """Record a host interface for a bounded time in the background; one recording at a time."""
        if not INTERFACE.fullmatch(interface or "") or not Path("/sys/class/net", interface).exists():
            raise ValueError("Unknown host interface")
        seconds = int(seconds)
        if not 1 <= seconds <= MAX_HOST_CAPTURE_SECONDS:
            raise ValueError(f"duration must be 1 to {MAX_HOST_CAPTURE_SECONDS} seconds")
        if capture_filter and not DISPLAY_FILTER.fullmatch(capture_filter):
            raise ValueError("Invalid capture filter")
        if not self._host_lock.acquire(blocking=False):
            raise CaptureUnavailable("A host capture is already running")
        name = f"host-{interface}-{time.strftime('%Y%m%d-%H%M%S')}.pcapng"
        arguments = ["tshark", "-i", interface, "-a", f"duration:{seconds}", "-a", f"filesize:{MAX_HOST_CAPTURE_BYTES // 1024}",
                     "-w", str(self.directory / name), *(["-f", capture_filter] if capture_filter else [])]

        def run():
            try:
                subprocess.run(arguments, capture_output=True, timeout=seconds + 15)
            except (OSError, subprocess.TimeoutExpired):
                pass
            finally:
                self._host_lock.release()
        try:
            threading.Thread(target=run, daemon=True).start()
        except BaseException:
            self._host_lock.release()
            raise
        return name
