#!/usr/bin/env bash
# #3088 (LD-146): unexec 4 関数 (5c1030 / 737d10 / 7ff6e0 / d243c0) の native 実行条件を整えて wasm と突合する。
# 原因: 全 case が [this+off] の読み出しで segv する。this = 引数 0 (rcx) は VMT 経由で
#   call [VMT+slot] する (5c1030 / d243c0 は slot 3 = 0x18、737d10 / 7ff6e0 は slot 47 = 0x178)。
#   this を arena+0x1000 の疑似オブジェクトにし、vmt blob (VMT 仮 proc 8 slot) を当てる。
#   0x178 の slot は vmt の範囲外のため、vptr を arena+0x1e88 (= 0x2000-0x178) に差し替えて slot 0 (仮 proc) を指す。
# 前提: FL_WIN64_DIR (fl-win64 の extracted/block00031_PE.bin)・tools/liftdiff/work/m11 (work-m11/work-liftdiff)。
# 使い方: bash tools/m11/ldfix/unexec4_3088.sh [OUTDIR]   (既定 $RUNNER_TEMP/unexec4_3088)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
LD="$HERE/../../liftdiff"
OUT="${1:-${RUNNER_TEMP:-/tmp}/unexec4_3088}"
mkdir -p "$OUT"
cd "$LD"
ST="$PWD/work/m11/boot_state.json"
run() {
  local va=$1 args=$2 patch=${3:-}
  local extra=()
  [ -n "$patch" ] && extra=(--patch "$patch")
  python3 liftdiff.py run targets/m11.json --fn "$va" --state "$ST" --args "$args" --blob vmt "${extra[@]}" --json "$OUT/$va.r$REP.json"
}
for REP in 1 2 3; do
  run 5c1030 "i:a:0x1000,i:0x5"
  run 737d10 "i:a:0x1000,i:0x5" "a:0x1000:q=a:0x1e88"
  run 7ff6e0 "i:a:0x1000,i:0x5" "a:0x1000:q=a:0x1e88"
  run d243c0 "i:a:0x1000"
done
python3 - "$OUT" <<'PY'
import json, sys, os
out = sys.argv[1]
for va in ['5c1030', '737d10', '7ff6e0', 'd243c0']:
    vs = []
    for rep in (1, 2, 3):
        r = json.load(open(os.path.join(out, '%s.r%d.json' % (va, rep))))
        c = r['cases'][0]
        tags = ','.join(t['tag'] for t in r.get('tags', []))
        vs.append('%s native=%s wasm=%s tags=%s' % (r['verdict'], c.get('native_status'), c.get('wasm_status'), tags))
    print('%s: x3 %s' % (va, ' | '.join(sorted(set(vs))) if len(set(vs)) == 1 else 'DIFF ' + ' | '.join(vs)))
PY
