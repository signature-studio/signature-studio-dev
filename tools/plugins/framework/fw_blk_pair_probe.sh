#!/usr/bin/env bash
# fw_blk_pair_probe.sh — #5165: BLK slot 0x18 の先頭 2 byte の値だけを変えた variant で、
# RetDec が 8a1018 を constant global にするかを数える (残りの BLK は 0 埋め)。
#   RETDEC_BIN=<retdec-decompiler> bash fw_blk_pair_probe.sh
# 入力: work/fw/fw_icall.dll (work-fw-stage1)。出力: work/blk/probe_* (gitignore)。
# 結果の読み方は REPORT_4270.md §11。
set -uo pipefail
: "${RETDEC_BIN:?RETDEC_BIN に retdec-decompiler のパスを指定する}"
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
W="$HERE/../work/blk"
SRC="$HERE/../work/fw/fw_icall.dll"
RANGE="0x804cf0-0x80577e"
mkdir -p "$W"
cd "$W"

python3 - "$SRC" <<'PY'
import struct, sys
src = open(sys.argv[1], 'rb').read()
pe = struct.unpack_from('<I', src, 0x3c)[0]
nsec = struct.unpack_from('<H', src, pe + 6)[0]
opt = struct.unpack_from('<H', src, pe + 20)[0]
so = pe + 24 + opt
ic = next(so + 40 * i for i in range(nsec) if src[so + 40 * i:so + 40 * i + 8].rstrip(b'\0') == b'.icall')
vs, va, rs, rp = struct.unpack_from('<IIII', src, ic + 8)
off = rp + (0x8A1000 - 0x400000 - va)
BLK = 0x280
pairs = {
  'p0000': b'\x00\x00', 'p0024': b'\x00\x24', 'p2000': b'\x20\x00', 'p2400': b'\x24\x00',
  'p2401': b'\x24\x01', 'p2402': b'\x24\x02', 'p2403': b'\x24\x03', 'p2411': b'\x24\x11',
  'p2420': b'\x24\x20', 'p2421': b'\x24\x21', 'p2424': b'\x24\x24', 'p2441': b'\x24\x41',
  'p24fe': b'\x24\xfe', 'p2500': b'\x25\x00', 'p2501': b'\x25\x01', 'p25ff': b'\x25\xff',
  'p2600': b'\x26\x00', 'p2700': b'\x27\x00', 'p247e': b'\x24\x7e', 'p2e00': b'\x2e\x00',
  'p7e00': b'\x7e\x00', 'p245f': b'\x24\x5f', 'p2409': b'\x24\x09', 'p240a': b'\x24\x0a',
  'p247f': b'\x24\x7f', 'p2480': b'\x24\x80', 'p7f00': b'\x7f\x00',
}
for name, pair in pairs.items():
    b = bytearray(BLK)
    b[0x18:0x1a] = pair
    d = bytearray(src)
    d[off:off + BLK] = bytes(b)
    open('probe_%s.dll' % name, 'wb').write(bytes(d))
PY

printf '%-10s %-14s\n' variant const_globals
for f in probe_p*.dll; do
  v="${f%.dll}"
  rm -f "$v.ll"
  timeout 200 "$RETDEC_BIN" "$f" -o "$v.c" --select-ranges "$RANGE" --select-decode-only --timeout 150 > "$v.log" 2>&1
  n=0
  [ -f "$v.ll" ] && n=$(grep -c '^@global_var_8a10' "$v.ll")
  printf '%-10s %-14s\n' "$v" "$n"
done
