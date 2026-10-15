#!/usr/bin/env bash
# index_table_scan_selftest.sh — index_table_scan.py の負の対照 (ICALL-85 / #3089)。合成 PE で検出と非検出を確かめる。
#   合成 PE: .rdata 1 section (VA 0x1810c4000・VirtualSize 0x1c000) の表 0x1810df738 の a=3 (p=0x1810df744) に値を置く。
#   正 1: v=87,069 → 一致 1 件 (p=0x1810df744・a=3・site=180703b7c)。
#   正 2: v=87,075 → 一致 1 dword・site 2 件 (site=180703b7c,180703913)。
#   負 1: v=87,070 (どの site にも届かない値) → 一致 0 件。
#   負 2: 全 dword を 0 にする → 一致 0 件。
#   用法: bash tools/icall/diff/index_table_scan_selftest.sh   (rc=0 で全件 PASS)
#   作業は $RUNNER_TEMP (無ければ $TMPDIR・/tmp) に置く。tools/**/work/ は使わない。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
W="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/index_scan_selftest.$$"
mkdir -p "$W"
trap 'rm -rf "$W"' EXIT
python3 - "$W" <<'PY'
import struct, sys
W = sys.argv[1]
RAW = 0x400
SIZE = 0x1C000
TABLE = 0x1810DF738
def make(name, value):
    d = bytearray(RAW + SIZE)
    struct.pack_into("<2s", d, 0, b"MZ")
    struct.pack_into("<I", d, 0x3C, 0x80)
    d[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", d, 0x84, 0x8664, 1, 0, 0, 0, 0xF0, 0x2022)
    struct.pack_into("<8sIIII", d, 0x188, b".rdata\0\0", SIZE, 0x10C4000, SIZE, RAW)
    if value is not None:
        p = TABLE + 4 * 3
        struct.pack_into("<i", d, RAW + (p - 0x1810C4000), value)
    open(f"{W}/{name}.bin", "wb").write(bytes(d))
make("pos1", 87069)
make("pos2", 87075)
make("neg1", 87070)
make("neg2", None)
PY
SCAN="python3 $HERE/index_table_scan.py"
rc=0
check() {
  local name="$1" file="$2" want="$3" out rdata
  out="$($SCAN "$file" 2>&1)"
  rdata="$(grep -F '.rdata' <<< "$out" | head -1)"
  if grep -qF -- "$want" <<< "$out"; then echo "PASS $name ($rdata 期待 '$want')"; else echo "FAIL $name ('$want' が無い: $rdata)"; rc=1; fi
}
check_none() {
  local name="$1" file="$2" out rdata
  out="$($SCAN "$file" 2>&1)"
  rdata="$(grep -F '.rdata' <<< "$out" | head -1)"
  if grep -qF '一致=0' <<< "$rdata" && ! grep -qF 'p=0x' <<< "$out"; then echo "PASS $name ($rdata)"; else echo "FAIL $name ($rdata)"; rc=1; fi
}
check "正1 (一致 1)" "$W/pos1.bin" "p=0x1810df744 v=87,069 a=3 site=180703b7c"
check "正2 (1 dword・site 2 件)" "$W/pos2.bin" "p=0x1810df744 v=87,075 a=3 site=180703b7c,180703913"
check_none "負1 届かない値 87,070 (一致 0)" "$W/neg1.bin"
check_none "負2 全 0 (一致 0)" "$W/neg2.bin"
exit $rc
