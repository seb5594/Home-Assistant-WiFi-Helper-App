"""Read-only local inventory: no network capabilities or radio mutations."""
import json
from pathlib import Path
from wifi_helper import Client

options = json.loads(Path('/data/options.json').read_text())
client = Client(options.get('wifi_helper_host'))
print(json.dumps(client.inventory(), indent=2))  # Diagnostics only; the helper is found by its host name.
