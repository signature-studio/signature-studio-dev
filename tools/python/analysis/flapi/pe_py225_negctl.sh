#!/usr/bin/env bash
# PY-225 (#3651) の走査 pe_py225_disp_scan.py のネガティブコントロール (1 コマンド)。
#   FL_WIN64_DIR=<展開先> bash tools/python/analysis/flapi/pe_py225_negctl.sh
# 対照: 存在しない disp (22f9) は 0 件 / 正の対照 (2304) は store を検出する /
#       VA 0x1186378 の lea の disp だけを 22fc から 22f8 に書き換えた複製 PE で 22fc が 2 件から 1 件に減る。
# 複製は $RUNNER_TEMP (無ければ $TMPDIR) 配下に作る (tools/**/work/ は使わない)。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SCAN="$HERE/pe_py225_disp_scan.py"
: "${FL_WIN64_DIR:?FL_WIN64_DIR に展開先を設定する}"
W="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/py225_negctl"
rm -rf "$W"
mkdir -p "$W/extracted"
cp "$FL_WIN64_DIR/extracted/block00031_PE.bin" "$W/extracted/"
python3 - "$W/extracted/block00031_PE.bin" <<'EOF'
import sys

import pefile

p = sys.argv[1]
raw = bytearray(open(p, "rb").read())
pe = pefile.PE(data=bytes(raw), fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
va = 0x1186378
off = None
for s in pe.sections:
    st = base + s.VirtualAddress
    if st <= va < st + s.Misc_VirtualSize:
        off = va - st + s.PointerToRawData
assert off is not None
assert bytes(raw[off:off + 7]) == bytes.fromhex("488d88fc220000"), bytes(raw[off:off + 7]).hex()
raw[off + 3:off + 7] = bytes.fromhex("f8220000")
open(p, "wb").write(bytes(raw))
print("mutant: VA 0x1186378 (file_off %s) の disp を 22fc -> 22f8 の 1 箇所に変更" % hex(off))
EOF
echo "原本 22fc: $(python3 "$SCAN" 22fc | sed -n 1p)"
echo "対照1 存在しない disp 22f9: $(python3 "$SCAN" 22f9 | sed -n 1p)"
echo "対照2 正の対照 store 2304: $(python3 "$SCAN" 2304 | sed -n 1p)"
echo "対照2 の store に 0x1186371 が含まれる: $(python3 "$SCAN" 2304 | grep -c '^  0x1186371 ')"
echo "複製 22fc: $(FL_WIN64_DIR="$W" python3 "$SCAN" 22fc | sed -n 1p)"
echo "複製 22f8: $(FL_WIN64_DIR="$W" python3 "$SCAN" 22f8 | sed -n 1p)"
