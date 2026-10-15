#!/usr/bin/env bash
# fw_blk_const_repro.sh — #4270: RetDec が BLK slot を `constant` global にする条件の最小再現.
#   bash fw_blk_const_repro.sh
# 入力: work/fw/fw_icall.dll (work-fw-stage1)。出力: work/blk/ (gitignore)。
# RetDec 本体は環境変数 RETDEC_BIN (retdec-decompiler のパス) で指定する (docs/REFERENCES.md の [RETDEC])。
# 手順: 再配置後の BLK (VA 0x8A1000 = RVA 0x4A1000) の 0x280 byte を variant ごとに書き換え、
#       その BLK を読む関数 (新 VA 0x804cf0〜0x80577e = 元 VA 0x43b130) だけを RetDec で decode する。
#       `^@global_var_8a10` の行数 (constant global の数) と BLK 直読みの行数を数える。
set -euo pipefail
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

def out(name, data):
    open(name + '.dll', 'wb').write(bytes(data))

def blank(fill):
    b = bytearray(src)
    b[off:off + BLK] = bytes([fill]) * BLK
    return b

def keep_only(lo, hi):
    b = blank(0)
    b[off + lo:off + hi] = src[off + lo:off + hi]
    return b

out('base', src)
out('zero', blank(0))
out('nop', blank(0x90))
out('only08', keep_only(0x08, 0x10))
out('only18', keep_only(0x18, 0x20))

# #4503: slot 0x18 (8 byte) の 1 byte ずつを 0 / 0xff に変えた variant (元 BLK から 1 byte だけ変える)。
def byte_set(i, val):
    b = bytearray(src)
    b[off + 0x18 + i] = val
    return b

for i in range(8):
    out('b18_%d_00' % i, byte_set(i, 0x00))
    out('b18_%d_ff' % i, byte_set(i, 0xff))
# "24 00" (0x18 の先頭 2 byte) を同時に 0 にした variant。
b = bytearray(src)
b[off + 0x18:off + 0x1a] = b'\x00\x00'
out('b18_pair_00', b)
# "24 00" だけを残し、0x18 の残り 6 byte を 0 にした variant (十分性の確認)。
out('b18_keep24', keep_only(0x18, 0x1a))
PY

REPS="${REPS:-1}"
printf '%-10s %-4s %-14s %-10s\n' variant rep const_globals blk_loads
for v in base zero nop only08 only18 $(ls "$W" | sed -n 's/^\(b18_[0-9a-z_]*\)\.dll$/\1/p'); do
  for r in $(seq 1 "$REPS"); do
    rm -f "$v.ll"
    timeout 200 "$RETDEC_BIN" "$v.dll" -o "$v.c" \
      --select-ranges "$RANGE" --select-decode-only --timeout 150 > "$v.log" 2>&1
    printf '%-10s %-4s %-14s %-10s\n' "$v" "$r" "$(grep -c '^@global_var_8a10' "$v.ll")" "$(grep -c 'inttoptr (i64 90480' "$v.ll")"
  done
done
