#!/bin/sh
# S2 build pinned to CivSwitchLDN's payload and installer, so the blobs match that launcher byte for byte.
# Defaults come from the vendored civswitchldn/; point LDN at a checkout to build from that instead.
# Override with KEYS / LDN / CORE / INSTALLER; extra args pass through (add --port, --flash).
set -e
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(dirname "$HERE")
KEYS=${KEYS:-$ROOT/prod.keys}
if [ -n "${LDN:-}" ]; then
  CORE=${CORE:-$LDN/payloads/core.js}
  INSTALLER=${INSTALLER:-$LDN/installer}
else
  CORE=${CORE:-$ROOT/civswitchldn/core.js}
  INSTALLER=${INSTALLER:-$ROOT/civswitchldn}
fi

[ -f "$KEYS" ] || { echo "E: no prod.keys at $KEYS - set KEYS=/path/prod.keys"; exit 2; }
[ -f "$CORE" ] || { echo "E: no core.js at $CORE - set CORE= or LDN="; exit 2; }
[ -f "$INSTALLER/install.py" ] || { echo "E: no installer at $INSTALLER - set INSTALLER= or LDN="; exit 2; }
echo "keys      $KEYS"
echo "core      $CORE"
echo "installer $INSTALLER"

export CIVSWITCH_KEYS=$KEYS CIVSWITCH_CORE=$CORE CIVSWITCH_INSTALLER_DIR=$INSTALLER
exec python3 "$ROOT/tools/build_and_flash.py" --docker --target esp32s2 "$@"
