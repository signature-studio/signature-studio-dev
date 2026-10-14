#!/usr/bin/env bash
# REPORT_2143 の数値を再現する手順 (#2143)。素材が必要:
#   PE       = fl-win64 の extracted/block00031_PE.bin
#   NORM0    = work-m11 の boot0..4.norm0.ll を置いたディレクトリ (tools/m11/work/ 相当)
#   BOOT_FINAL = M11_LDFIX=0 bash tools/m11/m11_gen_ir2.sh で作った work/boot_final.ll (ldfix 適用前。REPORT_2143 §1・§4 と同じ)
#   使い方: PE=... NORM0=... BOOT_FINAL=... bash tools/m11/ldfix/repro_2143.sh [all|audit|strip|f4|neg]
#   f4 は内部で f4on/f4off を作る。neg は f4 の出力 (OUT/2143_f4on.ll・f4off.ll) を前提とするため、単独実行時は先に f4 を走らせる。
# OUT (既定 ${RUNNER_TEMP:-/tmp}/2143) に生成物を置く。repo 内 work/ には書かない。
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
: "${PE:?PE=block00031_PE.bin のパス}"
: "${NORM0:?NORM0=boot0..4.norm0.ll のあるディレクトリ}"
OUT=${OUT:-${RUNNER_TEMP:-/tmp}/2143}
mkdir -p "$OUT"
step=${1:-all}
NORM_IN=("$NORM0"/boot0.norm0.ll "$NORM0"/boot1.norm0.ll "$NORM0"/boot2.norm0.ll "$NORM0"/boot3.norm0.ll "$NORM0"/boot4.norm0.ll)

# §1: 監査 (5 入力 norm0)。出力 sites = 分類された load 1 件ごと (REPORT §1 の表)。
audit() { # $1=出力名 $2..=入力
  local name=$1; shift
  time python3 "$HERE/audit_undefload_dest.py" "$PE" "$OUT/$name.json" "$@"
}

# §3: scan records (scan_text が返す load 1 件ごとの record。consumer 0 件も含む) と関数数
count_scan() {
  python3 - "$HERE" "$@" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from audit_undefload import scan_text, META_RE
recs, fns = 0, set()
chk = {}
for p in sys.argv[2:]:
    t = open(p, errors='replace').read()
    meta = {int(a): int(b) for a, b in META_RE.findall(t)}
    for r in scan_text(t, meta):
        recs += 1
        fns.add(r['fn'])
        if r['fn'] == 'function_132e8e0' and r['consumers']:
            chk[p.rsplit('/', 1)[-1]] = chk.get(p.rsplit('/', 1)[-1], 0) + len(r['consumers'])
print('scan records', recs, 'functions', len(fns), 'inputs', len(sys.argv) - 2)
print('function_132e8e0 scan sites (consumers >= 1) per input', chk)
PY
}

# §3: uselistorder 行を除いた入力を作る (実験)
strip() {
  mkdir -p "$OUT/stripped"
  for f in "${NORM_IN[@]}"; do
    sed '/^ *uselistorder /d' "$f" > "$OUT/stripped/$(basename "$f")"
  done
  count_scan "${NORM_IN[@]}"  | sed 's/^/[scan norm0] /'
  count_scan "$OUT"/stripped/boot*.norm0.ll | sed 's/^/[scan stripped] /'
  audit stripped "$OUT"/stripped/boot*.norm0.ll
}

# §4/§5 の入力: BOOT_FINAL = boot_final.ll (ldfix 適用前)。m11_gen_ir2.sh の M11_LDFIX=0 で作った IR を指定する。
# ldfix を F4 有無で 2 本かけ、F4 件数と xor 残骸数を出す。関数別の F4 件数は ldf4_ を含む関数ごとに集計する。
f4() {
  : "${BOOT_FINAL:?BOOT_FINAL=ldfix 適用前の boot_final.ll のパス}"
  python3 "$HERE/ldfix.py" "$BOOT_FINAL" "$OUT/2143_f4on.ll" --pe "$PE" --report "$OUT/f4on_report.json"
  python3 "$HERE/ldfix.py" "$BOOT_FINAL" "$OUT/2143_f4off.ll" --pe "$PE" --report "$OUT/f4off_report.json" --no-f4
  echo "ldf4 on=$(grep -c 'ldf4_' "$OUT/2143_f4on.ll" || true) off=$(grep -c 'ldf4_' "$OUT/2143_f4off.ll" || true)"
  echo "xor i64 0,0 on=$(grep -c 'xor i64 0, 0' "$OUT/2143_f4on.ll" || true) off=$(grep -c 'xor i64 0, 0' "$OUT/2143_f4off.ll" || true)"
  python3 - "$OUT/2143_f4on.ll" "$OUT/2143_f4off.ll" <<'PY'
import re, sys
def per_fn(p):
    t = open(p, errors='replace').read()
    res = {}
    for m in re.finditer(r'^define [^\n]*@(\w+)\(.*?^\}', t, re.S | re.M):
        res[m.group(1)] = len(re.findall(r'ldf4_', m.group(0)))
    return res
on, off = per_fn(sys.argv[1]), per_fn(sys.argv[2])
for fn in sorted(set(on) | set(off)):
    if on.get(fn) or off.get(fn):
        print('F4', fn, 'on', on.get(fn, 0), 'off', off.get(fn, 0))
PY
}

# §5: F4 有無の IR に dest 版監査を掛ける (ネガコン)
neg() {
  [ -f "$OUT/2143_f4on.ll" ] && [ -f "$OUT/2143_f4off.ll" ] || { echo "neg: 先に f4 を実行して $OUT/2143_f4on.ll・2143_f4off.ll を作ること" >&2; exit 1; }
  audit f4on "$OUT/2143_f4on.ll"
  audit f4off "$OUT/2143_f4off.ll"
}

# #2201 (LD-85): 名前付き stack_var の read を site にする監査 (--named)。F4 有無の差 = F4 修復の検出数。
named() {
  [ -f "$OUT/2143_f4on.ll" ] && [ -f "$OUT/2143_f4off.ll" ] || { echo "named: 先に f4 を実行すること" >&2; exit 1; }
  time python3 "$HERE/audit_undefload_dest.py" --named "$PE" "$OUT/named_f4on.json" "$OUT/2143_f4on.ll"
  time python3 "$HERE/audit_undefload_dest.py" --named "$PE" "$OUT/named_f4off.json" "$OUT/2143_f4off.ll"
  python3 - "$OUT" <<'PY'
import json, sys
E = sys.argv[1]
on = json.load(open(E + '/named_f4on.json')); off = json.load(open(E + '/named_f4off.json'))
key = lambda s: (s['fn'], s['load'], s['sv'], s['off'])
ko = {key(s) for s in on['sites']}; kf = {key(s) for s in off['sites']}
print('named on', len(ko), 'off', len(kf), 'diff(on-off)', len(ko - kf), 'diff(off-on)', len(kf - ko))
for t in ['132e8e0', '44d1c0', '69c360', '977e40', '865020']:
    print('named', t, 'on', sum(1 for k in ko if k[0] == t), 'off', sum(1 for k in kf if k[0] == t))
print('named diff functions', sorted({k[0] for k in ko - kf}))
PY
}

case "$step" in
  audit) audit norm0 "${NORM_IN[@]}" ;;
  strip) strip ;;
  f4) f4 ;;
  neg) neg ;;
  named) named ;;
  all) audit norm0 "${NORM_IN[@]}"; strip; f4; neg; named ;;
  *) echo "usage: $0 [all|audit|strip|f4|neg|named]" >&2; exit 2 ;;
esac
