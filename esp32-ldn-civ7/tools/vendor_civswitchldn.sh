#!/bin/sh
# Re-vendor CivSwitchLDN's installer assets into civswitchldn/ and report what changed.
set -e
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DST=$(dirname "$HERE")/civswitchldn
SRC=$1
[ -n "$SRC" ] || { echo "usage: $(basename "$0") /path/to/CivSwitchLDN"; exit 2; }
[ -f "$SRC/installer/install.py" ] || { echo "E: $SRC has no installer/install.py"; exit 2; }

for pair in "$SRC/payloads/core.js:core.js" "$SRC/installer/install.py:install.py" \
            "$SRC/installer/compress_stage.js:compress_stage.js" \
            "$SRC/installer/save_template.bin:save_template.bin"; do
  from=${pair%%:*}; to=${pair##*:}
  [ -f "$from" ] || { echo "E: missing $from"; exit 2; }
  if [ -f "$DST/$to" ] && cmp -s "$from" "$DST/$to"; then
    echo "same     $to"
  else
    cp "$from" "$DST/$to"
    echo "updated  $to  $(sha256sum "$DST/$to" | cut -c1-16)"
  fi
done
echo "source commit: $(sed -n 1p "$SRC/.git/refs/heads/main" 2>/dev/null || echo 'unknown - check .git')"
echo "if anything changed, refresh the sha256 table in $DST/VENDOR.md"
