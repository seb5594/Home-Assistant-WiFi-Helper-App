"""Read-only local inventory: no network capabilities or radio mutations."""
import json
from pathlib import Path
from wifi_helper import Client

options = json.loads(Path('/data/options.json').read_text())
client = Client(options['pairing_token'])
print(json.dumps(client.inventory(), indent=2))  # Contains diagnostics, never the pairing secret.
