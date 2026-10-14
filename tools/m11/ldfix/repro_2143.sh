#!/usr/bin/env bash
# REPORT_2143 の数値を再現する手順 (#2143)。素材 (fl-win64 の PE・work-m11 の norm0) が必要。
#   PE=<block00031_PE.bin> NORM0=<norm0 の置き場 (boot0..4.norm0.ll を含む)> BOOT_FINAL=<boot_final.ll> \
#     bash tools/m11/ldfix/repro_2143.sh [all|audit|strip|f4|neg]
# OUT (既定 ${RUNNER_TEMP:-/tmp}/2143) に生成物を置く。repo 内 work/ には書かない。
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
: "${PE:?PE=block00031_PE.bin のパス}"
: "${NORM0:?NORM0=boot0..4.norm0.ll のあるディレクトリ}"
OUT=${OUT:-${RUNNER_TEMP:-/tmp}/2143}
mkdir -p "$OUT"
step=${1:-all}
NORM_IN=("$NORM0"/boot0.norm0.ll "$NORM0"/boot1.norm0.ll "$NORM0"/boot2.norm0.ll "$NORM0"/boot3.norm0.ll "$NORM0"/boot4.norm0.ll)

# §1: 監査 (5 入力 norm0)。出力 sites = 分類された load 1 件ごと (下記 §0 の単位参照)。
audit() { # $1=出力名 $2..=入力
  local name=$1; shift
  time python3 "$HERE/audit_undefload_dest.py" "$PE" "$OUT/$name.json" "$@"
}

# §3 の scan 件数: scan_text が返す load 1 件ごとの record (consumer 0 件も含む) と関数数
count_scan() {
  python3 - "$HERE" "$@" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from audit_undefload import scan_text, META_RE
recs, fns = 0, set()
for p in sys.argv[2:]:
    t = open(p, errors='replace').read()
    meta = {int(a): int(b) for a, b in META_RE.findall(t)}
    for r in scan_text(t, meta):
        recs += 1
        fns.add(r['fn'])
print('scan records', recs, 'functions', len(fns), 'inputs', len(sys.argv) - 2)
PY
}

# uselistorder 行を除いた入力を作る (§3 の実験)
strip() {
  mkdir -p "$OUT/stripped"
  for f in "${NORM_IN[@]}"; do
    sed '/^ *uselistorder /d' "$f" > "$OUT/stripped/$(basename "$f")"
  done
}

# §4/§5: F4 有無の ldfix 出力 (boot_final.ll = M11_LDFIX=0 の ldfix 前 IR)
f4() {
  : "${BOOT_FINAL:?BOOT_FINAL=boot_final.ll のパス}"
  python3 "$HERE/ldfix.py" "$BOOT_FINAL" "$OUT/2143_f4on.ll" --pe "$PE" --report "$OUT/f4on_report.json"
  python3 "$HERE/ldfix.py" "$BOOT_FINAL" "$OUT/2143_f4off.ll" --pe "$PE" --report "$OUT/f4off_report.json" --no-f4
  grep -c 'ldf4_' "$OUT/2143_f4on.ll" || true
  grep -c 'ldf4_' "$OUT/2143_f4off.ll" || true
  grep -c 'xor i64 0, 0' "$OUT/2143_f4on.ll" "$OUT/2143_f4off.ll" || true
}

# §5: F4 有無の IR に dest 版監査を掛ける (ネガコン)
neg() {
  audit f4on "$OUT/2143_f4on.ll"
  audit f4off "$OUT/2143_f4off.ll"
}

case "$step" in
  audit) audit norm0 "${NORM_IN[@]}" ;;
  strip) strip; audit stripped "$OUT"/stripped/boot*.norm0.ll; count_scan "${NORM_IN[@]}"; count_scan "$OUT"/stripped/boot*.norm0.ll ;;
  f4) f4 ;;
  neg) neg ;;
  all) audit norm0 "${NORM_IN[@]}"; strip; audit stripped "$OUT"/stripped/boot*.norm0.ll; count_scan "${NORM_IN[@]}"; count_scan "$OUT"/stripped/boot*.norm0.ll; f4; neg ;;
  *) echo "usage: $0 [all|audit|strip|f4|neg]" >&2; exit 2 ;;
esac
