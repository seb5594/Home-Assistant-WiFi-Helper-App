#!/usr/bin/env bash
set -Eeuo pipefail
test -x /run.sh
bash -n /run.sh
python - <<'PY'
import api,broker,captures,inventory,lease,protocol,tickets,wifi
assert protocol.PROTOCOL_VERSION==4
assert protocol.SOCKET=='/share/wifi-helper-private/wifi.sock'
assert hasattr(lease,'Client')
print('PASS: standalone broker, SDK API and protocol-4 imports')
PY
iw --version
ip -Version
busctl --version
tshark --version | head -1
echo 'PASS: required bounded host-network tools'
