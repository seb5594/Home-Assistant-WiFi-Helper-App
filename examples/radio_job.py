"""Bounded client template. Runs only in an isolated app container, never on the host."""
import json
from pathlib import Path
import signal
import subprocess
import threading

from wifi_helper import Client


def main():
    stopped, lost = threading.Event(), threading.Event()
    for number in (signal.SIGTERM, signal.SIGINT):
        signal.signal(number, lambda *_: stopped.set())
    options = json.loads(Path('/data/options.json').read_text())
    client = Client(options['pairing_token'], lost=lost,
                    log=lambda level, text, channel: print(f'{level} [{channel}] {text}', flush=True))
    eligible = [item for item in client.inventory()['adapters'] if item['eligible']]
    interface = options.get('interface', '')
    if not interface and len(eligible) == 1:
        interface = eligible[0]['name']
    if not any(item['name'] == interface for item in eligible):
        raise RuntimeError('Select exactly one eligible adapter in app Configuration and restart')
    radio = client.acquire(interface)
    workers = []
    try:
        # Replace this bounded, read-only demonstration with your own guarded workflow.
        # Every fixed child command must target radio.interface and remain in this container.
        subprocess.run(['iw', 'dev', radio.interface, 'info'], check=True, timeout=8)
        for _ in range(30):
            if stopped.wait(1) or lost.is_set():
                break
    finally:
        # Your application must own and reap all processes using the radio.
        for worker in workers:
            worker.terminate()
            try:
                worker.wait(3)
            except subprocess.TimeoutExpired:
                worker.kill(); worker.wait(3)
        radio.release()
    if lost.is_set():
        raise RuntimeError('Helper connection lost; container must stop for recovery')
    return 0


if __name__ == '__main__':
    # Never swallow acquisition/return errors and leave a still-running namespace behind.
    raise SystemExit(main())
