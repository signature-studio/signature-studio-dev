#!/usr/bin/env bash
# dispatch_calls.py の識別力を確認するネガティブコントロール (対照 = golden 一致で rc 0、壊したものが rc 1)。
#   NC1: golden の selector 1 件を改変 (sel 2 → 3) → rc 1
#   NC2: golden から 1 件落とす (件数不足) → rc 1
#   NC3: golden に存在しない呼出し先を足す (件数超過) → rc 1
#   NC4: 殻のコピーで 1 site (0x8439d1) の rcx 由来 mov の disp32 を 0x1b8 → 0x1c8 に書換え、engine 8 件 → rc 1
# 判定は rc と「expect: 」行の有無の両方で行う (Python 例外で rc 1 になる偽陽性を防ぐ)。
# exit 0 = 全て期待通り
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
PE="$FL_WIN64_DIR/extracted/block23663_PE.bin"
GOLD=0x846ab0:2,0x846af4:4,0x846b3c:3,0x846b8f:5,0x8439d1:10,0x847220:11,0x8473c8:13,0x8474ad:14,0x847547:12
MUT="$(mktemp -d "${RUNNER_TEMP:-/tmp}/dispatch_nc.XXXXXX")"
trap 'rm -rf "$MUT"' EXIT
python3 - "$PE" "$MUT/mut.bin" "$HERE" 0x8439d1 <<'PY'
import sys
sys.path.insert(0, sys.argv[3])
import pefile
import dispatch_calls as dc
src, dst, site = sys.argv[1], sys.argv[2], int(sys.argv[4], 16)
pe = pefile.PE(src)
base = pe.OPTIONAL_HEADER.ImageBase
sec = next(s for s in pe.sections if s.Name.rstrip(b'\0') == b'.text')
ins = next(r for r in dc.scan(src) if r[0] == site)[2][0]
off = sec.PointerToRawData + ins.address - (base + sec.VirtualAddress)
data = bytearray(open(src, 'rb').read())
assert bytes(data[off + ins.size - 4: off + ins.size]) == b'\xb8\x01\x00\x00', ins.op_str
data[off + ins.size - 4: off + ins.size] = b'\xc8\x01\x00\x00'
open(dst, 'wb').write(bytes(data))
PY
FAIL=0
run() { # run <label> <期待 rc> <golden> [PE]
  local pe="${4:-$PE}" out rc
  set +e; out="$(python3 "$HERE/dispatch_calls.py" "$pe" --expect="$3" 2>&1)"; rc=$?; set -e
  if [ "$rc" = "$2" ] && grep -q '^expect: ' <<<"$out"; then echo "ok   $1 rc=$rc"; else echo "!!   $1: rc=$rc 期待 $2" >&2; FAIL=1; fi
}
run "対照 (golden 一致)" 0 "$GOLD"
run "NC1 selector 改変" 1 "${GOLD/0x846ab0:2/0x846ab0:3}"
run "NC2 件数不足" 1 "${GOLD%,0x847547:12}"
run "NC3 件数超過" 1 "$GOLD,0x847600:1"
run "NC4 殻側 1 site の engine 呼出しを改変 (engine 8 件)" 1 "$GOLD" "$MUT/mut.bin"
exit $FAIL
