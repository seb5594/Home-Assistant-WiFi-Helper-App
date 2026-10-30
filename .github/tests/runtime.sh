#!/usr/bin/env bash
set -Eeuo pipefail
test -x /run.sh
bash -n /run.sh
python - <<'PY'
import broker,inventory,lease,protocol,wifi
assert protocol.PROTOCOL_VERSION==3
assert protocol.SOCKET=='/share/wifi-helper-private/wifi.sock'
assert hasattr(lease,'Client')
print('PASS: standalone broker, SDK API and protocol-3 imports')
PY
iw --version
ip -Version
busctl --version
echo 'PASS: required bounded host-network tools'
