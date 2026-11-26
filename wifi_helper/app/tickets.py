"""Short-lived, single-use tickets that connect an HTTP request to one socket session."""
import secrets
import threading
import time

from protocol import OPERATIONS, TICKET_LENGTH, validate_interface

TICKET_TTL = 30
MAX_OUTSTANDING = 8


class TicketStore:
    """Issues tickets over HTTP and redeems each of them exactly once on the private socket."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._tickets = {}

    def _expire(self):
        now = self._clock()
        for ticket in [key for key, (_, _, deadline) in self._tickets.items() if deadline <= now]:
            del self._tickets[ticket]

    def issue(self, operation, interface):
        """Return a new ticket valid for one ``operation`` on one ``interface``."""
        if operation not in OPERATIONS:
            raise ValueError("Unknown operation")
        validate_interface(interface)
        with self._lock:
            self._expire()
            if len(self._tickets) >= MAX_OUTSTANDING:
                raise ValueError("Too many pending tickets; retry in a few seconds")
            ticket = secrets.token_hex(TICKET_LENGTH // 2)
            self._tickets[ticket] = (operation, interface, self._clock() + TICKET_TTL)
            return ticket

    def redeem(self, ticket):
        """Consume a ticket and return ``(operation, interface)``; unknown or expired tickets raise."""
        with self._lock:
            self._expire()
            entry = self._tickets.pop(ticket, None)
        if entry is None:
            raise ValueError("Unknown or expired ticket")
        return entry[0], entry[1]
