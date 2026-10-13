#!/usr/bin/env bash
# M11 IR 生成 (再現用): boot0..4.lift.ll → merge → numfix → asmfix → passes → genstubs → dotfix → fnclex0 rename
#   boot4 = tail-call/間接 call 表 seed の追加分 (m11_tail.py 出力)
set -euo pipefail
cd "$(dirname "$0")"
CH="work/boot0.lift.ll work/boot1.lift.ll work/boot2.lift.ll work/boot3.lift.ll"
[ -f work/boot4.lift.ll ] && CH="$CH work/boot4.lift.ll"
python3 m11_merge.py $CH -o work/boot_all.ll
python3 - <<'PYnum'
import re
d = 'work/boot_all.ll'
s = open(d).read()
names = sorted(set(int(x) for x in re.findall(r'^@(\d+) = ', s, re.M)))
s2 = re.sub(r'(?<![\w$.])@(\d+)\b', lambda m: '@m11num_%s' % m.group(1), s)
open(d, 'w').write(s2)
print('[numfix] numeric globals:', len(names))
PYnum
python3 m11_asmfix.py work/boot_all.ll work/boot_allfx.ll
python3 m11_passes.py work/boot_allfx.ll work/boot_final.ll --report work/ir_report.json --init-list work/inits_text.txt
python3 m11_genstubs.py work/boot_final.ll work
python3 - <<'PY2'
import re
d = 'work/boot_final.ll'
s = open(d).read()
s = re.sub(r'@([A-Za-z_][\w]*)\.\d+\b', lambda m: '@%s_D%s' % (m.group(1), m.group(0).split('.')[-1]), s)
# argless fnclex: 同一シンボル(i64)共存回避 (m11_rt.c が __asm_fnclex0 を C 実装)
s = s.replace('@__asm_fnclex__112', '@__asm_fnclex0')
open(d, 'w').write(s)
print('[dotfix+fnclex0] done')
PY2
# ldfix (CAB-231/CAB-131): load 取り違え (値↔アドレス / 1 段 deref 脱落) 修復 pass を常設適用する。
#   capstone による実機械語 (.pdata 区間) との突合付き。詳細は ldfix/REPORT.md / ldfix/REPORT_CAB131.md。
#   適用位置は m11_post (weak 化/sigfix) 前 = ここ (ldfix REPORT §6-2 の推奨)。
PE="${PE:-${FL_WIN64_DIR:-/home/ubuntu/work/analysis/win64}/extracted/block00031_PE.bin}"
if [ -f "$PE" ] && python3 -c 'import capstone, pefile' 2>/dev/null; then
  python3 ldfix/ldfix.py work/boot_final.ll work/boot_final.ldfix.ll --pe "$PE" --report work/ldfix_report.json ${LDFIX_ARGS:-}
  mv work/boot_final.ldfix.ll work/boot_final.ll
else
  echo "[gen_ir2] WARNING: ldfix skip (PE または capstone/pefile 無し)" >&2
fi
echo "[gen_ir2] OK: work/boot_final.ll ($(wc -l < work/boot_final.ll) 行)"
