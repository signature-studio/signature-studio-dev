#!/usr/bin/env bash
# PLG-F2-2 (#514) ネガティブコントロール: icall_gate.py が「復元なし / site 欠落 / 帰属不明」で FAIL (exit 1) することを確認する。
#   bash tools/plugins/f2/nc_icall.sh      (前提: f2_step2.sh 実行済み = work/batch/*, work/closure/*)
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
source "$ROOT/../shared/env.sh"
[ -f "$HERE/env.sh" ] && source "$HERE/env.sh"
cd "$ROOT"
N=work/f2/nc_icall; rm -rf "$N"; mkdir -p "$N"
B=18984; BB=$(printf %05d $B); PE="$FL_WIN64_DIR/extracted/block${BB}_PE.bin"; RG="work/closure/block$BB.ranges.txt"; IR="work/batch/$B/p.final.ll"
G() { python3 f2/icall_gate.py --pe "$PE" --ranges "$RG" --ir "$1" --label "$2"; }
echo "[OK ] 正常 (復元あり) IR:"; G "$IR" ok | tail -2; rc_ok=${PIPESTATUS[0]}
# NC1: 復元を外す (PLUG_ICALL=0 で同じ閉包を lift) → 間接 call が IR から消えて F1/F2
PLUG_ICALL=0 bash lift/lift_ranges.sh "$PE" "$RG" "$N/off" p 600 > "$N/off.log" 2>&1
echo "[NC1] 復元を外した IR (PLUG_ICALL=0):"; G "$N/off/p.final.ll" nc1_no_restore | tail -2; rc1=${PIPESTATUS[0]}
# NC2: 正常 IR から dispatch 呼出しを 1 行だけ削除 → missing=1 (F1)
python3 - "$IR" "$N/drop1.ll" <<'PY'
import re, sys
L = open(sys.argv[1]).read().split('\n')
i = next(k for k, l in enumerate(L) if '@__icall_dispatch(i64' in l and l.lstrip().startswith('call'))
print('削除: line %d: %s' % (i + 1, L[i].strip()))
del L[i]
open(sys.argv[2], 'w').write('\n'.join(L))
PY
echo "[NC2] dispatch を 1 本削除した IR:"; G "$N/drop1.ll" nc2_drop1 | tail -2; rc2=${PIPESTATUS[0]}
# NC3: dispatch の site VA を 0 にする (帰属失敗) → F3 と F1
python3 - "$IR" "$N/zero1.ll" <<'PY'
import re, sys
s = open(sys.argv[1]).read()
s = re.sub(r'(call void @__icall_dispatch\(i64 )\d+(\))', r'\g<1>0\2', s, count=1)
open(sys.argv[2], 'w').write(s)
PY
echo "[NC3] dispatch の site VA を 0 にした IR:"; G "$N/zero1.ll" nc3_zero1 | tail -2; rc3=${PIPESTATUS[0]}
# NC4: waiver の悪用 — NC2 で落とした site に waiver を付けても、raw IR にその VA の命令が残っているので waiver 無効 (F4) で FAIL
python3 - "$N/drop1.ll" "$N/waiver_bad.json" <<'PY'
import json, re, sys
# NC2 で消した dispatch の site VA = 正常 IR にあって drop1.ll に無い値
ok = set(re.findall(r'__icall_dispatch\(i64 (\d+)\)', open('work/batch/18984/p.final.ll').read()))
dr = re.findall(r'__icall_dispatch\(i64 (\d+)\)', open(sys.argv[1]).read())
gone = [v for v in ok if dr.count(v) < re.findall(r'__icall_dispatch\(i64 (\d+)\)', open('work/batch/18984/p.final.ll').read()).count(v)]
assert len(gone) == 1, gone
json.dump([{'block': 'nc', 'site': hex(int(gone[0])), 'reason': 'NC4 偽の waiver'}], open(sys.argv[2], 'w'))
print('偽 waiver: site', hex(int(gone[0])))
PY
echo "[NC4] 偽 waiver (落とした site に waiver を付ける):"; python3 f2/icall_gate.py --pe "$PE" --ranges "$RG" --ir "$N/drop1.ll" --raw-ir "work/batch/$B/p.drc.restored.ll" --label nc --waivers "$N/waiver_bad.json" | tail -2; rc4=${PIPESTATUS[0]}
# NC5: 正当な waiver (18979) を外す → missing=1 で FAIL
echo '[]' > "$N/no_waiver.json"
echo "[NC5] waiver を外した 18979:"; python3 f2/icall_gate.py --waivers "$N/no_waiver.json" 18979 | tail -2; rc5=${PIPESTATUS[0]}
echo "== 判定: 正常 rc=$rc_ok (期待 0) / NC1 rc=$rc1 / NC2 rc=$rc2 / NC3 rc=$rc3 / NC4 rc=$rc4 / NC5 rc=$rc5 (期待 いずれも 1)"
[ "$rc_ok" = 0 ] && [ "$rc1" = 1 ] && [ "$rc2" = 1 ] && [ "$rc3" = 1 ] && [ "$rc4" = 1 ] && [ "$rc5" = 1 ] && echo "ALL DETECTED" || { echo "NOT DETECTED あり"; exit 1; }
